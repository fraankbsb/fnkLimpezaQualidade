import io
import json
import shutil
import subprocess
import sys
import tkinter as tk
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from tkinter import messagebox

IS_WIN = sys.platform == "win32"
CREATE_NEW_CONSOLE = 0x00000010 if IS_WIN else 0


def get_app_dir() -> Path:
    """Pasta onde o launcher (e o payload) vivem. Nunca hardcoda letra de
    disco: deriva de onde o proprio executavel/script esta rodando, entao
    funciona em qualquer PC/disco (C:, D:, pendrive, etc.)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()
UPDATE_CONFIG_PATH = APP_DIR / "update_config.json"
VERSION_PATH = APP_DIR / "version.json"


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config():
    cfg = load_json(UPDATE_CONFIG_PATH)
    if not cfg:
        raise RuntimeError(f"update_config.json não encontrado em: {UPDATE_CONFIG_PATH}")
    for key in ("repo", "entry_point", "app_title"):
        if key not in cfg:
            raise RuntimeError(f"update_config.json sem o campo obrigatório: {key}")
    return cfg


def load_local_version():
    data = load_json(VERSION_PATH, {"version": "0.0.0"})
    return str(data.get("version", "0.0.0"))


def normalize_version(v: str) -> str:
    v = v.strip()
    return v[1:] if v.lower().startswith("v") else v


def github_api_get(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "fnkLimpezaQualidade-launcher",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


SETUP_ASSET_NAME = "launcher_setup.zip"


def find_zip_asset(release_json):
    """Escolhe o zip de PAYLOAD (codigo do app) para a atualizacao - nunca o
    launcher_setup.zip (que contem o proprio launcher.exe). Uma release pode
    ter os dois assets; pegar o errado tentaria sobrescrever o launcher.exe
    enquanto ele esta rodando, o que o Windows bloqueia (PermissionError)."""
    assets = release_json.get("assets", [])
    for asset in assets:
        name = asset.get("name", "")
        if name.lower().startswith("payload_") and name.lower().endswith(".zip"):
            return asset.get("browser_download_url"), name
    for asset in assets:
        name = asset.get("name", "")
        if name.lower().endswith(".zip") and name.lower() != SETUP_ASSET_NAME:
            return asset.get("browser_download_url"), name
    return None, None


def download_and_extract(url: str, dest_dir: Path, log):
    log("Baixando pacote de atualização...")
    req = urllib.request.Request(url, headers={"User-Agent": "fnkLimpezaQualidade-launcher"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    log(f"Download concluído ({len(data) / 1024 / 1024:.1f} MB). Extraindo...")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # Sobrescreve apenas os arquivos que estao no zip - nada mais na pasta
        # e tocado (cookies/segredos, .git, etc. ficam intactos). Nunca escreve
        # por cima do launcher.exe em execucao, mesmo que ele venha no zip por
        # engano (defesa extra alem do find_zip_asset acima).
        for info in zf.infolist():
            if Path(info.filename).name.lower() == "launcher.exe":
                continue
            zf.extract(info, dest_dir)
    log("Atualização aplicada.")


def do_update(log):
    cfg = load_config()
    repo = cfg["repo"]
    log(f"Verificando atualizações em {repo}...")

    try:
        release = github_api_get(f"https://api.github.com/repos/{repo}/releases/latest")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("Nenhuma release publicada ainda neste repositório.")
        raise RuntimeError(f"Falha ao consultar o GitHub (HTTP {e.code}).")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Sem conexão com o GitHub: {e.reason}")

    remote_tag = release.get("tag_name", "")
    remote_version = normalize_version(remote_tag)
    local_version = normalize_version(load_local_version())

    log(f"Versão local: {local_version}  |  Versão disponível: {remote_version}")

    if remote_version == local_version:
        return False, local_version

    zip_url, zip_name = find_zip_asset(release)
    if not zip_url:
        raise RuntimeError("A release mais recente não tem um arquivo .zip anexado.")

    download_and_extract(zip_url, APP_DIR, log)
    new_version = normalize_version(load_local_version())
    return True, new_version


def do_start(cfg, log):
    entry_point = APP_DIR / cfg["entry_point"]
    if not entry_point.exists():
        raise RuntimeError(f"Arquivo principal não encontrado: {entry_point}\n"
                            f"Clique em \"Atualizar App\" primeiro.")

    python_exe = shutil.which("python") or shutil.which("py") or "python"
    kwargs = {}
    if IS_WIN:
        kwargs["creationflags"] = CREATE_NEW_CONSOLE
    subprocess.Popen([python_exe, str(entry_point)], cwd=str(APP_DIR), **kwargs)
    log(f"Iniciado: {entry_point.name}")


class LauncherApp:
    def __init__(self, root):
        self.root = root
        try:
            self.cfg = load_config()
        except Exception as e:
            messagebox.showerror("Erro de configuração", str(e))
            root.destroy()
            sys.exit(1)

        root.title(self.cfg["app_title"])
        root.geometry("420x220")
        root.resizable(False, False)

        tk.Label(root, text=self.cfg["app_title"], font=("Segoe UI", 13, "bold")).pack(pady=(18, 4))
        self.version_var = tk.StringVar(value=f"Versão instalada: {load_local_version()}")
        tk.Label(root, textvariable=self.version_var, font=("Segoe UI", 9)).pack(pady=(0, 14))

        tk.Button(root, text="🔄 Atualizar App", font=("Segoe UI", 11), width=24,
                  command=self.on_update).pack(pady=6)
        tk.Button(root, text="▶ Iniciar App", font=("Segoe UI", 11), width=24,
                  bg="#0078D4", fg="white", command=self.on_start).pack(pady=6)

        self.status_var = tk.StringVar(value="Pronto.")
        tk.Label(root, textvariable=self.status_var, font=("Segoe UI", 8), fg="#555").pack(
            side="bottom", pady=10)

    def log(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def on_update(self):
        try:
            updated, version = do_update(self.log)
        except Exception as e:
            messagebox.showerror("Erro ao atualizar", str(e))
            self.log("Falha ao atualizar.")
            return

        self.version_var.set(f"Versão instalada: {version}")
        if updated:
            messagebox.showinfo("Atualizado", f"App atualizado para a versão {version}.")
        else:
            messagebox.showinfo("Atualizado", f"Você já está na versão mais recente ({version}).")
        self.log("Pronto.")

    def on_start(self):
        try:
            do_start(self.cfg, self.log)
        except Exception as e:
            messagebox.showerror("Erro ao iniciar", str(e))


def main():
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
