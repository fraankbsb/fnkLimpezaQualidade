# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A batch video processor for repurposing downloaded pet/comedy clips: strips original
metadata and replaces it with fake iPhone 15 Pro Max metadata, applies a "unicização"
filter chain (subtle speed/pitch/hue/noise changes) so platforms don't flag re-uploads
as duplicates, boosts sharpness/contrast/brightness, and automatically detects and
blurs the original creator's `@handle` watermark — without touching captions or other
on-screen text. Content is used under license from the original creators (confirmed
with the user; do not extend this assumption to other projects).

Ships two independent things:
1. **The app** (`fnk_app.py` + `fnk_pipeline.py` + `fnk_watermark.py`) — the actual
   video processor, run directly or via the launcher.
2. **The launcher/auto-update system** (`launcher.py`, `publish.py`,
   `watch_and_publish.py`) — a self-updating distribution mechanism so the compiled
   `launcher.exe` never needs rebuilding; only the app source is redistributed, via
   GitHub Releases.

## Commands

Run the app directly (dev mode, no launcher):
```
python fnk_app.py
```

Run headless, no GUI (used for testing/automation):
```
python fnk_app.py --cli <pasta_entrada> <pasta_saida>
```

Publish a new release (bumps `version.json`, commits, pushes, zips the payload,
creates a GitHub release):
```
python publish.py auto                    # auto-bumps patch version, timestamp message
python publish.py 1.2.0 "mensagem aqui"    # explicit version + message
```

Watch payload files and auto-publish 8s after the last change settles:
```
iniciar_vigia.bat          # or: python watch_and_publish.py
```

Rebuild the launcher (only needed if `launcher.py` itself changes — the app payload
does **not** require this):
```
python -m PyInstaller --noconfirm --onefile --windowed --name launcher launcher.py
copy dist\launcher.exe .   # launcher.exe must live next to update_config.json/version.json
```

Rebuild the standalone all-in-one exe (bundles Python/opencv/numpy, no system deps —
different from the launcher flow, useful for one-off/non-technical distribution):
```
python -m PyInstaller --noconfirm --windowed --name fnkLimpezaQualidade --add-data "resources\frozen_east_text_detection.pb;resources" fnk_app.py
```

No test suite exists. Verification during development has been done by running the
detection/pipeline functions directly against real sample videos and inspecting
extracted frames (see conversation history / commit messages for the methodology:
frame extraction via `ffmpeg -update 1 -frames:v 1`, SSIM/PSNR comparisons for encoder
changes, hash comparisons for update-download integrity).

## Architecture

### Video pipeline (`fnk_watermark.py` → `fnk_pipeline.py` → `fnk_app.py`)

`fnk_app.py:process_folder()` is the single entry point both the GUI and the
`--cli` mode call. It walks the input folder recursively, mirrors the folder
structure into the output folder, and per video:

1. **Watermark detection** (`fnk_watermark.find_watermark_regions`) — samples ~16
   frames spread across the video, runs OpenCV's EAST text detector
   (`resources/frozen_east_text_detection.pb`, CLAHE-enhanced input to catch
   low-opacity text) on each. Detections are grouped into horizontal "bands" across
   frames (`_cluster_bands`) rather than matched by exact position, because
   low-opacity watermark text gets detected as different fragments frame to frame —
   the band union reassembles the full text from partial per-frame catches. Only
   bands persistent across ≥40% of sampled frames survive (`min_coverage_ratio`).
   **Then an OCR pass** (`_verify_regions_have_handle`, via `pytesseract`/Tesseract)
   discards any surviving region whose text doesn't match `@\w` — this is what
   distinguishes an actual `@handle` from captions ("POV: Cachorros"), app branding
   without an `@` (e.g. a plain "GUTOTV" logo), or false positives from physically
   static scene content in fixed-camera footage (dashcam console buttons, mirror,
   windshield glare — these are just as "persistent across frames" as a real
   watermark, so position/persistence alone isn't sufficient). If Tesseract isn't
   installed, this filter is skipped and the pipeline falls back to blurring any
   persistent region (see `fnk_app.ensure_tesseract_installed`, which tries to
   silently `winget install` it first).

2. **ffmpeg command construction** (`fnk_pipeline.build_ffmpeg_cmd`) — builds one
   `-filter_complex` graph combining the quality filter chain (unsharp, eq,
   lenscorrection, noise, deflicker, hue, speed/pitch) with a per-region blur: each
   detected region is `split` off, cropped, `gblur`'d, and alpha-feathered (via a
   `geq` alpha ramp, `BLUR_FEATHER` px) before being `overlay`'d back — this gives a
   soft-edged patch instead of a visible rectangle. All quality/blur constants live
   as module-level globals at the top of `fnk_pipeline.py`.

3. **Encoding** — `get_best_encoder()` probes `h264_nvenc` → `h264_qsv` → `h264_amf`
   → `libx264` with a throwaway 3-frame test encode and caches whichever works for
   the rest of the run. This is a runtime capability check, not a hardcoded choice —
   different PCs have different GPUs (or none), and it must degrade to `libx264`
   cleanly everywhere. Same bitrate/preset target across encoders, so this only
   affects speed, not output quality (validated via SSIM/PSNR against libx264 output
   before adopting).

4. **Metadata** — original metadata is stripped (`-map_metadata -1`) and replaced
   with fake Apple/iPhone metadata (constants in `fnk_pipeline.py`).

Threading model: `fnk_app.App` runs `process_folder` in a background thread; all
UI updates go through a `queue.Queue` polled by `root.after` (`_poll_queue`) —
tkinter widgets are never touched from the worker thread directly.

### Launcher / auto-update system

Three independent scripts, each with a specific job, tied together by two small
JSON files that live next to the compiled `launcher.exe`:

- `update_config.json` — `{repo, entry_point, app_title}`, essentially static.
- `version.json` — `{version}`, rewritten by every `publish.py` run and by every
  `launcher.py` update-download (the zip always contains the new `version.json`,
  so extracting it is what makes the local version match).

**`launcher.py`** (compiled once to `launcher.exe`, never needs recompiling after):
reads those two files, and on "Atualizar App" hits
`GET api.github.com/repos/{repo}/releases/latest`, compares `tag_name` to local
`version.json`, and if different downloads the release's `.zip` asset and
`zipfile.extractall()`s it directly over the app folder — this only touches files
actually present in the zip, so anything not in `GIT_PAYLOAD_FILES`/
`ZIP_EXTRA_PATHS` (e.g. a future `cookies/` secrets folder) is never touched. "Iniciar
App" runs `entry_point` via `subprocess.Popen([python, entry_point], creationflags=
CREATE_NEW_CONSOLE)` — this requires a system Python with the project's
dependencies (`requirements.txt`) installed on whatever machine runs it; it is not a
frozen/bundled execution. All paths are derived from `Path(sys.executable).resolve()
.parent` when frozen (never a hardcoded drive letter), so the same exe works
regardless of which PC/drive it's copied to.

**`publish.py`**: `GIT_PAYLOAD_FILES` (small source files, git-tracked) vs
`ZIP_EXTRA_PATHS` (currently just `resources/`, the ~92MB EAST model — deliberately
**not** git-tracked to avoid bloating repo history with a third-party binary, but
still read straight off disk and included in every release zip). `find_gh()` resolves
the `gh` CLI via `shutil.which` first, falling back to the hardcoded Program Files
path, since a scheduled/background invocation may not have an interactive shell's
PATH. Version bumps are always patch-level in `auto` mode; commits are skipped
gracefully (not treated as an error) when there's nothing staged, which matters
because `watch_and_publish.py` calls `publish.py auto` on every detected change.

**`watch_and_publish.py`**: polls mtimes of `GIT_PAYLOAD_FILES`-equivalent
(`WATCHED_FILES`) every 2s; on change, waits for 8s of silence before calling
`publish.py auto`, so a burst of saves collapses into one release instead of one per
save.

### Editing-machine gotcha

On the PC where the source is actually edited, "Atualizar App" in the launcher is
redundant and can be actively harmful: it downloads and extracts the last
*published* release over the local files, silently discarding any local edit that
hasn't been published yet (vigia not running, or mid-change). On that machine, only
"Iniciar App" should be used.

### Portability constraints (why some code looks the way it does)

The user works across multiple PCs with different drive letters. Anything that
resolves a path to itself or its data directory must derive it at runtime
(`Path(__file__).resolve()` / `Path(sys.executable).resolve()`), never hardcode
`C:`/`D:`. This has already shaped `launcher.py`'s `get_app_dir()` and should be
followed for any new default paths.

### External dependencies this project assumes are present on PATH

`ffmpeg`/`ffprobe`, `gh` (authenticated), and — since the OCR watermark filter was
added — `tesseract` (auto-installed via `winget install UB-Mannheim.TesseractOCR` on
first run if missing; see `fnk_app.ensure_tesseract_installed`). None of these are
bundled into the git-tracked payload.
