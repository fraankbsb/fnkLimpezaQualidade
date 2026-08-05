import subprocess
import json

CODEC_VIDEO = "libx264"
BITRATE_VIDEO = "6M"
PRESET = "medium"
BITRATE_AUDIO = "192k"
FPS_SAIDA = "60"

META_MAKE = "Apple"
META_MODEL = "iPhone 15 Pro Max"
META_SOFTWARE = "17.5.1"
META_CREATION = "2024-09-15T10:23:44"

TRIM_START = 0.1
SPEED = 1.005
PITCH = 1.02
HUE = 2
NOISE = 1
DEFLICKER = True
LENS = True
FADE = 0.3
EQ_AUDIO = True

UNSHARP_LUMA = 1.8
EQ_CONTRAST = 1.10
EQ_SATURATION = 1.15
EQ_BRIGHTNESS = 0.04
EQ_GAMMA = 1.03

BLUR_SIGMA = 25
BLUR_STEPS = 3
BLUR_FEATHER = 12  # px de degrade nas bordas do blur, para ficar impercepitivel

VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")


def probe_duration_and_size(ffprobe_path, path):
    out = subprocess.run(
        [ffprobe_path, "-v", "error", "-show_entries",
         "format=duration:stream=width,height", "-select_streams", "v:0",
         "-of", "json", path],
        capture_output=True, text=True
    )
    data = json.loads(out.stdout or "{}")
    dur = float(data.get("format", {}).get("duration", 5.0) or 5.0)
    streams = data.get("streams", [])
    w = int(streams[0]["width"]) if streams else 0
    h = int(streams[0]["height"]) if streams else 0
    return dur, w, h


def _quality_filter_chain():
    vf = "unsharp=5:5:{:.2f}:5:5:0.0".format(UNSHARP_LUMA)
    vf += ",eq=contrast={:.2f}:saturation={:.2f}:brightness={:.2f}:gamma={:.2f}".format(
        EQ_CONTRAST, EQ_SATURATION, EQ_BRIGHTNESS, EQ_GAMMA)
    if HUE != 0:
        vf += f",hue=h={HUE}"
    if LENS:
        vf += ",lenscorrection=k1=0.01:k2=0.01"
    if NOISE != 0:
        vf += f",noise=alls={NOISE}:allf=t"
    if DEFLICKER:
        vf += ",deflicker=size=2:mode=am"
    if abs(SPEED - 1.0) > 1e-6:
        vf += f",setpts=PTS/{SPEED}"
    return vf


def _fade_filter(dur_seg):
    if FADE <= 0:
        return ""
    fout = max(1, int(dur_seg - 1))
    return f",fade=t=in:st=0:d={FADE},fade=t=out:st={fout}:d={FADE}"


def build_video_filtergraph(regions, dur_seg):
    """Builds the -filter_complex graph string and returns (graph, out_label)."""
    vf = _quality_filter_chain() + _fade_filter(dur_seg) + ",format=yuv420p"

    if not regions:
        graph = f"[0:v]{vf}[vout]"
        return graph, "[vout]"

    n = len(regions)
    split_labels = "".join(f"[vsrc{i}]" for i in range(n))
    graph = f"[0:v]{vf},split={n + 1}[vmain]{split_labels};"

    alpha_expr = f"255*min(1\\,min(min(X\\,W-X)\\,min(Y\\,H-Y))/{BLUR_FEATHER})"
    geq = f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='{alpha_expr}'"

    for i, (x, y, w, h) in enumerate(regions):
        graph += (f"[vsrc{i}]crop={w}:{h}:{x}:{y},"
                   f"gblur=sigma={BLUR_SIGMA}:steps={BLUR_STEPS},format=yuva420p,{geq}[vblur{i}];")

    prev = "vmain"
    for i, (x, y, w, h) in enumerate(regions):
        out_lbl = "vout" if i == n - 1 else f"vtmp{i}"
        graph += f"[{prev}][vblur{i}]overlay={x}:{y}:format=auto[{out_lbl}];"
        prev = out_lbl
    graph = graph.rstrip(";")
    return graph, "[vout]"


def build_audio_filter(dur_seg):
    af = ""
    if abs(PITCH - 1.0) > 1e-6:
        if abs(SPEED - 1.0) > 1e-6:
            af = f"asetrate=44100*{PITCH},aresample=44100,atempo={SPEED}"
        else:
            af = f"asetrate=44100*{PITCH},aresample=44100"
    else:
        if abs(SPEED - 1.0) > 1e-6:
            af = f"atempo={SPEED}"

    if EQ_AUDIO:
        eqchain = "equalizer=f=60:width_type=o:width=2:g=-1,equalizer=f=12000:width_type=o:width=2:g=-1"
        af = f"{af},{eqchain}" if af else eqchain

    if FADE > 0:
        afout = max(1, int(dur_seg - 1))
        fadechain = f"afade=t=in:st=0:d={FADE},afade=t=out:st={afout}:d={FADE}"
        af = f"{af},{fadechain}" if af else fadechain

    return af


def build_ffmpeg_cmd(ffmpeg_path, in_path, out_path, regions, dur_seg):
    graph, out_label = build_video_filtergraph(regions, dur_seg)
    af = build_audio_filter(dur_seg)

    cmd = [ffmpeg_path, "-hide_banner", "-nostdin"]
    if TRIM_START > 0:
        cmd += ["-ss", str(TRIM_START)]
    cmd += ["-i", in_path,
            "-map_metadata", "-1", "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1",
            "-fflags", "+bitexact",
            "-filter_complex", graph,
            "-map", out_label, "-map", "0:a?",
            "-r", FPS_SAIDA,
            "-c:v", CODEC_VIDEO, "-b:v", BITRATE_VIDEO, "-preset", PRESET,
            "-c:a", "aac", "-b:a", BITRATE_AUDIO]
    if af:
        cmd += ["-af", af]
    cmd += ["-f", "mov", "-brand", "qt", "-movflags", "+faststart",
            "-metadata", f"make={META_MAKE}",
            "-metadata", f"model={META_MODEL}",
            "-metadata", f"software={META_SOFTWARE}",
            "-metadata", f"creation_time={META_CREATION}",
            "-metadata:s:v", "handler_name=Core Media Video",
            "-metadata:s:v", "encoder=",
            "-metadata:s:a", "handler_name=Core Media Audio",
            "-metadata:s:a", "encoder=",
            out_path, "-y"]
    return cmd
