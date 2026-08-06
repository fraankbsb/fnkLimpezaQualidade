import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
VERSION_PATH = PROJECT_DIR / "version.json"

REPO = "fraankbsb/fnkLimpezaQualidade"

# Arquivos versionados no git (fonte). O modelo de deteccao (resources/) fica
# de fora do git por ser um binario de terceiros de ~92MB - ele so entra no
# zip da release (ver ZIP_EXTRA_PATHS), lido direto do disco.
GIT_PAYLOAD_FILES = [
    "fnk_app.py",
    "fnk_pipeline.py",
    "fnk_watermark.py",
    "update_config.json",
    "version.json",
    "requirements.txt",
]

# Pastas/arquivos adicionais que entram SÓ no zip da release (o launcher
# baixa e extrai isso por cima da pasta do app).
ZIP_EXTRA_PATHS = [
    "resources",
]

# Pacote separado (mesmo nome em toda release) so com o necessario pra
# instalar do zero num PC novo: launcher.exe + os dois JSONs de config.
# Como o nome do asset nunca muda, o link
# github.com/<repo>/releases/latest/download/launcher_setup.zip
# fica valido pra sempre, mesmo depois de novas releases.
LAUNCHER_SETUP_FILES = ["launcher.exe", "update_config.json"]
LAUNCHER_SETUP_NAME = "launcher_setup.zip"


def find_gh() -> str:
    gh = shutil.which("gh")
    if gh:
        return gh
    fallback = Path(r"C:\Program Files\GitHub CLI\gh.exe")
    if fallback.exists():
        return str(fallback)
    raise RuntimeError(
        "Não encontrei o executável 'gh' (GitHub CLI) no PATH nem em "
        f"{fallback}. Instale o GitHub CLI ou ajuste find_gh() em publish.py."
    )


def run(cmd, **kwargs):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_DIR, text=True, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"Comando falhou (exit {result.returncode}): {' '.join(str(c) for c in cmd)}")
    return result


def read_local_version() -> str:
    if not VERSION_PATH.exists():
        return "0.0.0"
    with open(VERSION_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("version", "0.0.0")


def bump_patch(version: str) -> str:
    parts = version.split(".")
    while len(parts) < 3:
        parts.append("0")
    major, minor, patch = parts[0], parts[1], parts[2]
    try:
        patch = str(int(patch) + 1)
    except ValueError:
        patch = "1"
    return f"{major}.{minor}.{patch}"


def write_version(version: str):
    with open(VERSION_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": version}, f, indent=2)
        f.write("\n")


def build_zip(version: str) -> Path:
    zip_path = PROJECT_DIR / f"payload_v{version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    import zipfile
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in GIT_PAYLOAD_FILES:
            src = PROJECT_DIR / rel
            if src.exists():
                zf.write(src, arcname=rel)
            else:
                print(f"[aviso] payload ausente, pulando: {rel}")
        for rel in ZIP_EXTRA_PATHS:
            src = PROJECT_DIR / rel
            if src.is_dir():
                for f in src.rglob("*"):
                    if f.is_file():
                        zf.write(f, arcname=str(f.relative_to(PROJECT_DIR)))
            elif src.is_file():
                zf.write(src, arcname=rel)
            else:
                print(f"[aviso] payload ausente, pulando: {rel}")
    return zip_path


def build_launcher_setup_zip() -> Path | None:
    missing = [p for p in LAUNCHER_SETUP_FILES if not (PROJECT_DIR / p).exists()]
    if missing:
        print(f"[aviso] launcher_setup.zip nao gerado, faltando: {missing}")
        return None

    import zipfile
    zip_path = PROJECT_DIR / LAUNCHER_SETUP_NAME
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in LAUNCHER_SETUP_FILES:
            zf.write(PROJECT_DIR / rel, arcname=rel)
    return zip_path


def git_publish(version: str, message: str):
    add_paths = [p for p in GIT_PAYLOAD_FILES if (PROJECT_DIR / p).exists()]
    run(["git", "add", *add_paths])

    status = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=PROJECT_DIR)
    if status.returncode == 0:
        print("Nada novo para commitar (versão local já igual à publicada).")
    else:
        run(["git", "commit", "-m", message])
    run(["git", "push"])


def gh_release(gh_exe: str, version: str, message: str, assets: list[Path]):
    tag = f"v{version}"
    run([gh_exe, "release", "create", tag, *[str(a) for a in assets],
         "--repo", REPO, "--title", tag, "--notes", message])


def main():
    if len(sys.argv) < 2:
        print("Uso: python publish.py <versao> [mensagem]")
        print("     python publish.py auto")
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "auto":
        version = bump_patch(read_local_version())
        message = f"Auto-publish {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    else:
        version = arg
        message = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else f"Release {version}"

    print(f"Publicando versão {version} — {message}")

    gh_exe = find_gh()

    write_version(version)
    git_publish(version, message)
    zip_path = build_zip(version)
    assets = [zip_path]
    setup_zip = build_launcher_setup_zip()
    if setup_zip:
        assets.append(setup_zip)
    gh_release(gh_exe, version, message, assets)

    print(f"OK: v{version} publicada em {REPO}.")


if __name__ == "__main__":
    main()
