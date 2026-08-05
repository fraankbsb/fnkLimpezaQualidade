import os
import re
import shutil

import cv2
import numpy as np
import pytesseract

_AT_HANDLE_RE = re.compile(r"@\w")


def _configure_tesseract():
    exe = shutil.which("tesseract")
    if not exe:
        fallback = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(fallback):
            exe = fallback
    if exe:
        pytesseract.pytesseract.tesseract_cmd = exe
    return exe


_TESSERACT_PATH = _configure_tesseract()


def ensure_tesseract_ready():
    """Reexecuta a deteccao do tesseract e atualiza o estado do modulo.
    Chame isso depois de instalar o Tesseract em tempo de execucao (ex:
    fnk_app.ensure_tesseract_installed) para nao precisar reiniciar o app."""
    global _TESSERACT_PATH
    _TESSERACT_PATH = _configure_tesseract()
    return _TESSERACT_PATH


def load_east_net(model_path):
    return cv2.dnn.readNet(model_path)


def _decode_predictions(scores, geometry, min_conf):
    numRows, numCols = scores.shape[2:4]
    rects, confidences = [], []
    for y in range(numRows):
        scoresData = scores[0, 0, y]
        xData0 = geometry[0, 0, y]
        xData1 = geometry[0, 1, y]
        xData2 = geometry[0, 2, y]
        xData3 = geometry[0, 3, y]
        anglesData = geometry[0, 4, y]
        for x in range(numCols):
            if scoresData[x] < min_conf:
                continue
            offsetX, offsetY = x * 4.0, y * 4.0
            angle = anglesData[x]
            cos, sin = np.cos(angle), np.sin(angle)
            h = xData0[x] + xData2[x]
            w = xData1[x] + xData3[x]
            endX = int(offsetX + (cos * xData1[x]) + (sin * xData2[x]))
            endY = int(offsetY - (sin * xData1[x]) + (cos * xData2[x]))
            startX = int(endX - w)
            startY = int(endY - h)
            rects.append((startX, startY, endX, endY))
            confidences.append(float(scoresData[x]))
    return rects, confidences


def detect_text_boxes(frame_bgr, net, min_conf=0.15):
    H, W = frame_bgr.shape[:2]
    newW = max(32, (W // 32) * 32)
    newH = max(32, (H // 32) * 32)
    rW, rH = W / float(newW), H / float(newH)

    resized = cv2.resize(frame_bgr, (newW, newH))

    lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    enhanced = cv2.cvtColor(cv2.merge([l2, a, b]), cv2.COLOR_LAB2BGR)

    blob = cv2.dnn.blobFromImage(enhanced, 1.0, (newW, newH),
                                  (123.68, 116.78, 103.94), swapRB=True, crop=False)
    net.setInput(blob)
    scores, geometry = net.forward(["feature_fusion/Conv_7/Sigmoid", "feature_fusion/concat_3"])
    rects, confidences = _decode_predictions(scores, geometry, min_conf)
    idxs = cv2.dnn.NMSBoxes(rects, confidences, min_conf, 0.4)

    boxes = []
    if len(idxs) > 0:
        for i in idxs.flatten():
            sX, sY, eX, eY = rects[i]
            sX, eX = int(sX * rW), int(eX * rW)
            sY, eY = int(sY * rH), int(eY * rH)
            sX, sY = max(0, sX), max(0, sY)
            eX, eY = min(W, eX), min(H, eY)
            if eX > sX and eY > sY:
                boxes.append((sX, sY, eX, eY))
    return boxes


def _union_rect(rects):
    x1 = min(r[0] for r in rects)
    y1 = min(r[1] for r in rects)
    x2 = max(r[2] for r in rects)
    y2 = max(r[3] for r in rects)
    return (x1, y1, x2, y2)


def _rects_close(r1, r2, x_gap, y_gap):
    x1a, y1a, x2a, y2a = r1
    x1b, y1b, x2b, y2b = r2
    ex1, ey1, ex2, ey2 = x1a - x_gap, y1a - y_gap, x2a + x_gap, y2a + y_gap
    return not (x2b < ex1 or x1b > ex2 or y2b < ey1 or y1b > ey2)


def _merge_close_rects(rects, x_gap=22, y_gap=10):
    changed = True
    rects = list(rects)
    while changed:
        changed = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                if _rects_close(rects[i], rects[j], x_gap, y_gap):
                    rects[i] = _union_rect([rects[i], rects[j]])
                    del rects[j]
                    changed = True
                    break
            if changed:
                break
    return rects


def _cluster_bands(all_boxes_per_frame, y_tol=16, x_gap=60):
    """Group text regions that recur on the same horizontal line across frames,
    even if each frame only catches a fragment of the full watermark text
    (common with very low-opacity text, where EAST's confidence per glyph run
    varies frame to frame). Bands accumulate the union of every fragment seen
    on that line so partial detections still add up to full text coverage.
    Returns list of dicts: {frames:set(), rect:(x1,y1,x2,y2)}
    """
    bands = []
    for frame_idx, boxes in enumerate(all_boxes_per_frame):
        # merge same-frame fragments on the same line first
        line_rects = _merge_close_rects(list(boxes), x_gap=28, y_gap=8)
        for rect in line_rects:
            x1, y1, x2, y2 = rect
            ycenter = (y1 + y2) / 2.0
            placed = False
            for b in bands:
                if abs(b["ycenter"] - ycenter) <= y_tol and _rects_close(b["rect"], rect, x_gap, y_tol):
                    b["rect"] = _union_rect([b["rect"], rect])
                    b["frames"].add(frame_idx)
                    bx1, by1, bx2, by2 = b["rect"]
                    b["ycenter"] = (by1 + by2) / 2.0
                    placed = True
                    break
            if not placed:
                bands.append({"frames": {frame_idx}, "rect": rect, "ycenter": ycenter})
    return bands


def _ocr_crop_has_handle(crop_bgr):
    if crop_bgr.size == 0:
        return False
    h = crop_bgr.shape[0]
    scale = max(1.0, 64.0 / max(1, h))
    resized = cv2.resize(crop_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    for variant in (enhanced, cv2.bitwise_not(enhanced)):
        try:
            text = pytesseract.image_to_string(variant, config="--psm 6")
        except Exception:
            continue
        if _AT_HANDLE_RE.search(text):
            return True
    return False


def _verify_regions_have_handle(regions, kept_frames, max_frames_checked=6):
    if not _TESSERACT_PATH:
        # Tesseract nao disponivel neste PC: nao da pra confirmar o "@", entao
        # nao arrisca borrar frase/cena por engano - melhor pular a verificacao
        # e devolver a lista como veio (comportamento antigo).
        return regions

    verified = []
    for (x, y, w, h) in regions:
        found = False
        for frame in kept_frames[:max_frames_checked]:
            crop = frame[y:y + h, x:x + w]
            if _ocr_crop_has_handle(crop):
                found = True
                break
        if found:
            verified.append((x, y, w, h))
    return verified


def find_watermark_regions(video_path, net, n_samples=16, min_coverage_ratio=0.4,
                            y_tol=16, x_gap=60, pad=5, min_conf=0.12):
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total_frames <= 0 or W == 0 or H == 0:
        cap.release()
        return []

    n_samples = min(n_samples, max(1, total_frames))
    sample_idxs = sorted(set(int(total_frames * i / n_samples) for i in range(n_samples)))

    all_boxes_per_frame = []
    kept_frames = []
    for idx in sample_idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        boxes = detect_text_boxes(frame, net, min_conf=min_conf)
        all_boxes_per_frame.append(boxes)
        kept_frames.append(frame)
    cap.release()

    n_used = len(all_boxes_per_frame)
    if n_used == 0:
        return []

    bands = _cluster_bands(all_boxes_per_frame, y_tol=y_tol, x_gap=x_gap)
    min_frames = max(2, int(n_used * min_coverage_ratio))
    persistent = [b for b in bands if len(b["frames"]) >= min_frames]
    if not persistent:
        return []

    rects = _merge_close_rects([b["rect"] for b in persistent], x_gap=x_gap, y_gap=y_tol)

    candidates = []
    for (x1, y1, x2, y2) in rects:
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(W, x2 + pad)
        y2 = min(H, y2 + pad)
        candidates.append((x1, y1, x2 - x1, y2 - y1))  # x, y, w, h

    # so mantem regioes cujo texto realmente comeca com @ - descarta legendas/
    # frases e falsos positivos de cena estatica (console de carro, espelho, etc.)
    return _verify_regions_have_handle(candidates, kept_frames)
