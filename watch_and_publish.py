import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

WATCHED_FILES = [
    "fnk_app.py",
    "fnk_pipeline.py",
    "fnk_watermark.py",
    "update_config.json",
    "requirements.txt",
]

POLL_SECONDS = 2
QUIET_SECONDS = 8


def snapshot_mtimes():
    mtimes = {}
    for rel in WATCHED_FILES:
        p = PROJECT_DIR / rel
        mtimes[rel] = p.stat().st_mtime if p.exists() else None
    return mtimes


def publish_now():
    print(f"\n[{time.strftime('%H:%M:%S')}] Mudanças estabilizadas. Publicando...")
    result = subprocess.run([sys.executable, str(PROJECT_DIR / "publish.py"), "auto"],
                             cwd=PROJECT_DIR)
    if result.returncode == 0:
        print(f"[{time.strftime('%H:%M:%S')}] Publicação concluída.\n")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] Publicação falhou (exit {result.returncode}).\n")


def main():
    print(f"Vigia iniciado. Monitorando: {', '.join(WATCHED_FILES)}")
    print(f"Silêncio necessário antes de publicar: {QUIET_SECONDS}s\n")

    last_mtimes = snapshot_mtimes()
    last_change_at = None

    while True:
        time.sleep(POLL_SECONDS)
        current = snapshot_mtimes()

        if current != last_mtimes:
            print(f"[{time.strftime('%H:%M:%S')}] Alteração detectada.")
            last_mtimes = current
            last_change_at = time.time()
            continue

        if last_change_at is not None and (time.time() - last_change_at) >= QUIET_SECONDS:
            publish_now()
            last_change_at = None
            last_mtimes = snapshot_mtimes()


if __name__ == "__main__":
    main()
