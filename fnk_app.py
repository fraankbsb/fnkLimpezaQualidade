import os
import sys
import time
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import fnk_watermark as wm
import fnk_pipeline as pipe

APP_TITLE = "fnkLimpezaQualidade — Processador de Vídeos"
VIDEO_EXTS = pipe.VIDEO_EXTS

IS_WIN = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0


def resource_path(rel_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel_path)


def find_exe(name):
    from shutil import which
    return which(name)


def find_videos(root_dir):
    result = []
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(VIDEO_EXTS):
                result.append(os.path.join(dirpath, fn))
    return sorted(result)


def run_ffmpeg(cmd):
    kwargs = {}
    if IS_WIN:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def ensure_tesseract_installed(log_fn):
    """A deteccao de watermark so filtra corretamente por '@nome' se o
    Tesseract estiver instalado - sem ele, o app cairia num modo degradado
    (borraria qualquer texto persistente, sem checar o '@'). Em vez de deixar
    isso passar silencioso, instala sozinho via winget antes de processar."""
    if wm.ensure_tesseract_ready():
        return True

    log_fn("Tesseract-OCR não encontrado - instalando automaticamente (necessário "
           "para o filtro de '@nomedoperfil')...")
    winget = find_exe("winget")
    if not winget:
        log_fn("[AVISO] winget não encontrado. Instale o Tesseract-OCR manualmente: "
               "https://github.com/UB-Mannheim/tesseract/wiki")
        return False

    kwargs = {}
    if IS_WIN:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    try:
        subprocess.run(
            [winget, "install", "--id", "UB-Mannheim.TesseractOCR", "-e",
             "--silent", "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True, text=True, timeout=300, **kwargs)
    except Exception as e:
        log_fn(f"[AVISO] Falha ao instalar Tesseract automaticamente: {e}")
        return False

    if wm.ensure_tesseract_ready():
        log_fn("Tesseract-OCR instalado com sucesso.")
        return True

    log_fn("[AVISO] Tesseract não ficou disponível após a instalação. "
           "O filtro de '@nomedoperfil' ficará desativado nesta sessão.")
    return False


def process_folder(in_dir, out_dir, net_holder, log_fn, progress_fn=None, stop_event=None):
    """Core batch pipeline, free of any GUI toolkit dependency.
    net_holder: dict with key "net" used to lazily load/cache the EAST model across calls.
    log_fn(str), progress_fn(done, total) are plain callbacks (must be safe to call
    from whatever thread invokes process_folder).
    Returns (ok_count, err_count, total, elapsed_seconds).
    """
    t0 = time.time()
    ok_count = 0
    err_count = 0

    videos = find_videos(in_dir)
    total = len(videos)
    if total == 0:
        log_fn("Nenhum vídeo encontrado na pasta de entrada.")
        return 0, 0, 0, 0.0

    ensure_tesseract_installed(log_fn)

    if net_holder.get("net") is None:
        log_fn("Carregando modelo de detecção de marca d'água...")
        model_path = resource_path(os.path.join("resources", "frozen_east_text_detection.pb"))
        try:
            net_holder["net"] = wm.load_east_net(model_path)
        except Exception as e:
            log_fn(f"[ERRO] Falha ao carregar modelo de detecção: {e}")
            return 0, 0, total, time.time() - t0

    net = net_holder["net"]
    ffmpeg_path = find_exe("ffmpeg")
    ffprobe_path = find_exe("ffprobe")

    log_fn(f"{total} vídeo(s) encontrado(s). Iniciando processamento...\n")

    for i, in_path in enumerate(videos, start=1):
        if stop_event is not None and stop_event.is_set():
            log_fn("Processamento interrompido pelo usuário.")
            break

        rel = os.path.relpath(in_path, in_dir)
        rel_dir = os.path.dirname(rel)
        stem = os.path.splitext(os.path.basename(in_path))[0]
        out_subdir = os.path.join(out_dir, rel_dir) if rel_dir else out_dir
        os.makedirs(out_subdir, exist_ok=True)
        out_path = os.path.join(out_subdir, stem + ".mp4")

        # Pasta de saida igual a de entrada (processar "no lugar") faz o
        # ffmpeg recusar (nao escreve em cima do arquivo que esta lendo).
        # Nesse caso grava num temporario e so substitui o original depois
        # que o ffmpeg terminar com sucesso.
        same_file = os.path.normcase(os.path.abspath(out_path)) == os.path.normcase(os.path.abspath(in_path))
        build_target = os.path.join(out_subdir, f".{stem}.tmp{i}.mp4") if same_file else out_path

        log_fn(f"[{i}/{total}] {rel}")

        try:
            regions = wm.find_watermark_regions(in_path, net)
            if regions:
                log_fn(f"    marca d'água detectada: {len(regions)} região(ões) -> blur aplicado")
            else:
                log_fn("    nenhuma marca d'água detectada (nada será borrado)")

            dur, w, h = pipe.probe_duration_and_size(ffprobe_path, in_path)
            cmd = pipe.build_ffmpeg_cmd(ffmpeg_path, in_path, build_target, regions, dur)
            result = run_ffmpeg(cmd)

            success = result.returncode == 0 and os.path.exists(build_target) and os.path.getsize(build_target) > 0
            if success and same_file:
                os.replace(build_target, out_path)  # atomico - ffmpeg ja fechou a leitura do original
            elif not success and os.path.exists(build_target):
                os.remove(build_target)

            if success:
                ok_count += 1
                log_fn("    [OK]\n")
            else:
                err_count += 1
                log_fn(f"    [ERRO] ffmpeg retornou {result.returncode}")
                log_fn((result.stderr or "")[-800:] + "\n")
        except Exception as e:
            err_count += 1
            log_fn(f"    [ERRO] {e}\n")

        if progress_fn:
            progress_fn(i, total)

    elapsed = time.time() - t0
    log_fn("=" * 50)
    log_fn("RESUMO GERAL")
    log_fn(f"  Vídeos : {total}")
    log_fn(f"  OK     : {ok_count}")
    log_fn(f"  Erros  : {err_count}")
    log_fn(f"  Tempo  : {elapsed:.1f}s")
    log_fn("=" * 50)
    return ok_count, err_count, total, elapsed


class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("880x620")
        root.minsize(760, 520)

        self.in_dir = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto.")
        self.stop_event = threading.Event()
        self.worker = None
        self.event_queue = queue.Queue()
        self.net_holder = {"net": None}

        self._build_ui()
        self.root.after(120, self._poll_queue)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm_in = tk.Frame(self.root)
        frm_in.pack(fill="x", **pad)
        tk.Label(frm_in, text="Pasta de entrada (vídeos sem tratamento):", anchor="w").pack(fill="x")
        row = tk.Frame(frm_in)
        row.pack(fill="x")
        tk.Entry(row, textvariable=self.in_dir).pack(side="left", fill="x", expand=True)
        tk.Button(row, text="Procurar...", command=self._browse_in).pack(side="left", padx=(6, 0))

        frm_out = tk.Frame(self.root)
        frm_out.pack(fill="x", **pad)
        tk.Label(frm_out, text="Pasta de saída (vídeos tratados):", anchor="w").pack(fill="x")
        row2 = tk.Frame(frm_out)
        row2.pack(fill="x")
        tk.Entry(row2, textvariable=self.out_dir).pack(side="left", fill="x", expand=True)
        tk.Button(row2, text="Procurar...", command=self._browse_out).pack(side="left", padx=(6, 0))

        frm_btn = tk.Frame(self.root)
        frm_btn.pack(fill="x", **pad)
        self.btn_start = tk.Button(frm_btn, text="PROCESSAR", bg="#0078D4", fg="white",
                                    font=("Segoe UI", 10, "bold"), command=self._start)
        self.btn_start.pack(side="left")
        self.btn_stop = tk.Button(frm_btn, text="PARAR", command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(0, 4))

        tk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=10)

        frm_log = tk.Frame(self.root)
        frm_log.pack(fill="both", expand=True, padx=10, pady=10)
        self.log = tk.Text(frm_log, wrap="word", font=("Consolas", 9))
        sb = tk.Scrollbar(frm_log, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _browse_in(self):
        d = filedialog.askdirectory(title="Selecione a pasta de entrada")
        if d:
            self.in_dir.set(d)

    def _browse_out(self):
        d = filedialog.askdirectory(title="Selecione a pasta de saída")
        if d:
            self.out_dir.set(d)

    # -- thread-safe callbacks: only ever put onto the queue, never touch widgets directly --
    def _log(self, msg):
        self.event_queue.put(("log", msg))

    def _progress(self, done, total):
        self.event_queue.put(("progress", done, total))

    def _poll_queue(self):
        try:
            while True:
                item = self.event_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log.insert("end", item[1] + "\n")
                    self.log.see("end")
                elif kind == "progress":
                    _, done, total = item
                    self.progress.config(maximum=total, value=done)
                    self.status_var.set(f"Processando {done}/{total}")
                elif kind == "done":
                    self.status_var.set("Concluído.")
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _start(self):
        in_dir = self.in_dir.get().strip()
        out_dir = self.out_dir.get().strip()
        if not in_dir or not os.path.isdir(in_dir):
            messagebox.showerror("Erro", "Selecione uma pasta de entrada válida.")
            return
        if not out_dir:
            messagebox.showerror("Erro", "Selecione uma pasta de saída válida.")
            return
        if not find_exe("ffmpeg") or not find_exe("ffprobe"):
            messagebox.showerror("Erro", "FFmpeg/FFprobe não encontrado no PATH do sistema.\n"
                                          "Instale o FFmpeg e tente novamente.")
            return

        videos = find_videos(in_dir)
        if not videos:
            messagebox.showwarning("Aviso", "Nenhum vídeo encontrado na pasta de entrada.")
            return

        os.makedirs(out_dir, exist_ok=True)

        self.log.delete("1.0", "end")
        self.stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress.config(maximum=len(videos), value=0)

        self.worker = threading.Thread(target=self._run_worker, args=(in_dir, out_dir), daemon=True)
        self.worker.start()

    def _run_worker(self, in_dir, out_dir):
        process_folder(in_dir, out_dir, self.net_holder, self._log, self._progress, self.stop_event)
        self.event_queue.put(("done",))

    def _stop(self):
        self.stop_event.set()
        self._log("[Parar solicitado] finalizando o vídeo atual e encerrando...")


def run_cli(in_dir, out_dir):
    net_holder = {"net": None}
    ok, err, total, elapsed = process_folder(in_dir, out_dir, net_holder, print)
    return 0 if err == 0 else 1


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--cli":
        sys.exit(run_cli(sys.argv[2], sys.argv[3]))
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
