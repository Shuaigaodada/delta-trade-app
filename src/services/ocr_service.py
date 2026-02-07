import os
import re
import json
import time
import cv2
import numpy as np
from paddleocr import PaddleOCR

_OCR = None


def resolve_image_path(image_input):
    if image_input is None:
        return None
    if isinstance(image_input, str):
        return image_input
    if isinstance(image_input, dict):
        for k in ("path", "name", "file_path", "tempfile", "orig_name"):
            v = image_input.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def get_ocr():
    global _OCR
    if _OCR is None:
        _OCR = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            show_log=False,     
            drop_score=0.2  
        )
    return _OCR



def _imread_unicode(path: str):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data is None or data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _ocr_run(ocr_obj, img_obj):
    try:
        return ocr_obj.ocr(img_obj)
    except TypeError:
        return ocr_obj.ocr(img_obj, det=True, rec=True)


def _to_3ch(img):
    if img is None:
        return None
    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def _sharp(gray):
    # 轻微锐化，提升数字边缘
    k = np.array([[0, -1, 0],
                  [-1, 5, -1],
                  [0, -1, 0]], dtype=np.float32)
    return cv2.filter2D(gray, -1, k)


def _preprocess_variants(roi_bgr):
    """
    重点：别一上来就 adaptive threshold（会把 UI 纹理炸出来）
    """
    variants = []

    # 放大
    big = cv2.resize(roi_bgr, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    variants.append(("bgr_big", _to_3ch(big)))

    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)

    # 去噪 + 对比度
    gray_blur = cv2.bilateralFilter(gray, 7, 40, 40)
    variants.append(("gray_bilateral", _to_3ch(gray_blur)))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g = clahe.apply(gray_blur)
    variants.append(("gray_clahe", _to_3ch(g)))

    # 锐化
    g_sharp = _sharp(g)
    variants.append(("gray_sharp", _to_3ch(g_sharp)))

    # Otsu 二值（比 adaptive 更稳）
    _, thr = cv2.threshold(g_sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("thr_otsu", _to_3ch(thr)))
    variants.append(("thr_otsu_inv", _to_3ch(cv2.bitwise_not(thr))))

    # 形态学闭运算：把数字笔画连起来
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    close = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=1)
    variants.append(("thr_close", _to_3ch(close)))
    variants.append(("thr_close_inv", _to_3ch(cv2.bitwise_not(close))))

    return [(n, im) for (n, im) in variants if im is not None]


def _parse_texts_from_result(result):
    texts = []
    if result is None:
        return texts

    # 经典 PaddleOCR: [ [ [box, (text, score)], ... ] ]
    try:
        if isinstance(result, list) and result and isinstance(result[0], list):
            page = result[0]
            for item in page:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    ts = item[1]
                    if isinstance(ts, (list, tuple)) and len(ts) >= 1:
                        text = ts[0]
                        score = ts[1] if len(ts) > 1 else 1.0
                        if isinstance(text, str) and float(score) >= 0.08:
                            texts.append(text)
            return texts
    except Exception:
        pass

    # 兜底：把所有 str 都捞出来
    def walk(o):
        if isinstance(o, str):
            texts.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(result)
    return texts


def _extract_candidates_from_texts(texts):
    """
    支持 21,789K / 21789K / 21.7W / 2.1万
    返回单位：k（整数）
    """
    candidates_k = []
    candidates_plain = []

    for t in texts:
        s = (t or "").strip()

        # 带单位（允许逗号）
        for m in re.finditer(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKwW万])", s):
            raw = m.group(1).replace(",", "")
            unit = m.group(2).lower()
            try:
                num = float(raw)
            except Exception:
                continue
            if unit in ("w", "万"):
                candidates_k.append(int(round(num * 10000)))
            else:
                candidates_k.append(int(round(num)))

        # 纯数字兜底：21789 / 21,789
        for m in re.finditer(r"\b([0-9][0-9,]{3,})\b", s):
            raw = m.group(1).replace(",", "")
            try:
                candidates_plain.append(int(raw))
            except Exception:
                pass

    return candidates_k if candidates_k else candidates_plain


def _to_jsonable(obj):
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="ignore")
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    return str(obj)


def extract_pure_coin_k(image_input, debug: bool = False, debug_dir: str = "logs/ocr_debug"):
    os.makedirs(debug_dir, exist_ok=True)
    real_path = resolve_image_path(image_input)

    if debug:
        with open(os.path.join(debug_dir, "last_input.txt"), "w", encoding="utf-8") as f:
            f.write(f"time={time.ctime()}\n")
            f.write(f"type={type(image_input)}\n")
            f.write(f"raw={repr(image_input)}\n")
            f.write(f"resolved={real_path}\n")

    if not real_path or not os.path.exists(real_path):
        if debug:
            with open(os.path.join(debug_dir, "last_error.txt"), "w", encoding="utf-8") as f:
                f.write(f"file not found: {real_path}\n")
        return None

    img = _imread_unicode(real_path)
    if img is None:
        if debug:
            with open(os.path.join(debug_dir, "last_error.txt"), "w", encoding="utf-8") as f:
                f.write("imread failed\n")
        return None

    h, w = img.shape[:2]

    # ✅ 更精准 ROI：只截“纯币那串数字”
    # 你那张图纯币在右上角偏中，且在另一串数字左边
    roi_boxes = [
        (0.52, 0.00, 0.80, 0.18),  # 只覆盖 21,789K（推荐）
        (0.48, 0.00, 0.86, 0.22),  # 兜底更大一点
        (0.55, 0.00, 1.00, 0.22),  # 你原本的大 ROI（最后兜底）
    ]

    ocr = get_ocr()
    best = None

    for bi, (x1r, y1r, x2r, y2r) in enumerate(roi_boxes):
        x1 = max(0, int(w * x1r))
        y1 = max(0, int(h * y1r))
        x2 = min(w, int(w * x2r))
        y2 = min(h, int(h * y2r))

        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            continue

        variants = _preprocess_variants(roi)

        for vname, vimg in variants:
            if debug:
                out_path = os.path.join(debug_dir, f"roi{bi}_{vname}.png")
                try:
                    cv2.imencode(".png", vimg)[1].tofile(out_path)
                except Exception:
                    pass

            try:
                result = _ocr_run(ocr, vimg)
            except Exception as e:
                if debug:
                    with open(os.path.join(debug_dir, "last_error.txt"), "w", encoding="utf-8") as f:
                        f.write(f"ocr_run error: {e}\n")
                continue

            texts = _parse_texts_from_result(result)

            if debug:
                ts = int(time.time() * 1000)
                base = f"ocr_result_roi{bi}_{vname}_{ts}"

                # 原始结果
                with open(os.path.join(debug_dir, base + ".txt"), "w", encoding="utf-8") as f:
                    f.write(repr(result))
                try:
                    with open(os.path.join(debug_dir, base + ".json"), "w", encoding="utf-8") as f:
                        json.dump(_to_jsonable(result), f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

                # ✅ 额外：把 texts 单独写出来（你现在最需要看的就是这个）
                with open(os.path.join(debug_dir, base + "_texts.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(texts) if texts else "(no texts)\n")

            if not texts:
                continue

            candidates = _extract_candidates_from_texts(texts)
            if candidates:
                cand = max(candidates)
                if best is None or cand > best:
                    best = cand

    if debug and best is None:
        with open(os.path.join(debug_dir, "last_error.txt"), "w", encoding="utf-8") as f:
            f.write("no candidates found from OCR texts\n")

    return best
