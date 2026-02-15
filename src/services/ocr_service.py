# src/services/ocr_service.py
import os
import re
import cv2
import numpy as np
from paddleocr import PaddleOCR

_OCR = None
_OCR_NUM = None


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
            ocr_version="PP-OCRv3",
            show_log=False,
            drop_score=0.2,
        )
    return _OCR


def get_ocr_num():
    """
    数字专用 OCR：用于黑底白字、纯数字小截图
    - lang=en 对数字更稳
    - drop_score 降低，避免小图被过滤
    """
    global _OCR_NUM
    if _OCR_NUM is None:
        _OCR_NUM = PaddleOCR(
            use_angle_cls=False,
            lang="en",
            ocr_version="PP-OCRv3",
            show_log=False,
            drop_score=0.01,
        )
    return _OCR_NUM


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


def _ocr_rec_only(ocr_obj, img_obj):
    try:
        return ocr_obj.ocr(img_obj, det=False, rec=True)
    except Exception:
        return None


def _to_3ch(img):
    if img is None:
        return None
    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def _sharp(gray):
    k = np.array([[0, -1, 0],
                  [-1, 5, -1],
                  [0, -1, 0]], dtype=np.float32)
    return cv2.filter2D(gray, -1, k)


def _preprocess_variants(roi_bgr):
    variants = []

    big = cv2.resize(roi_bgr, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    variants.append(("bgr_big", _to_3ch(big)))

    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)

    gray_blur = cv2.bilateralFilter(gray, 7, 40, 40)
    variants.append(("gray_bilateral", _to_3ch(gray_blur)))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g = clahe.apply(gray_blur)
    variants.append(("gray_clahe", _to_3ch(g)))

    g_sharp = _sharp(g)
    variants.append(("gray_sharp", _to_3ch(g_sharp)))

    _, thr = cv2.threshold(g_sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("thr_otsu", _to_3ch(thr)))
    variants.append(("thr_otsu_inv", _to_3ch(cv2.bitwise_not(thr))))

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    close = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=1)
    variants.append(("thr_close", _to_3ch(close)))
    variants.append(("thr_close_inv", _to_3ch(cv2.bitwise_not(close))))

    return [(n, im) for (n, im) in variants if im is not None]


def _box_center_x(box) -> float | None:
    """
    PaddleOCR box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    返回中心点 x（像素）
    """
    try:
        xs = [p[0] for p in box]
        return float(sum(xs)) / float(len(xs))
    except Exception:
        return None


def _parse_items_from_result(result):
    """
    返回 items: [{"text": str, "score": float, "cx": float|None}]
    - det+rec：带 box -> cx 可用
    - rec-only：无 box -> cx=None
    """
    items = []
    if result is None:
        return items

    try:
        if not isinstance(result, list) or not result:
            return items
        page = result[0]

        if isinstance(page, list) and page:
            for it in page:
                # rec-only: (' 647,736', 0.87)
                if isinstance(it, (list, tuple)) and len(it) == 2 and isinstance(it[0], str):
                    text = it[0]
                    score = it[1]
                    try:
                        if float(score) >= 0.08:
                            items.append({"text": text, "score": float(score), "cx": None})
                    except Exception:
                        items.append({"text": text, "score": 0.0, "cx": None})
                    continue

                # det+rec: [box, (text, score)]
                if isinstance(it, (list, tuple)) and len(it) >= 2:
                    box = it[0]
                    ts = it[1]
                    if isinstance(ts, (list, tuple)) and len(ts) >= 1 and isinstance(ts[0], str):
                        text = ts[0]
                        score = ts[1] if len(ts) > 1 else 1.0
                        try:
                            if float(score) >= 0.08:
                                cx = _box_center_x(box)
                                items.append({"text": text, "score": float(score), "cx": cx})
                        except Exception:
                            pass
        return items
    except Exception:
        return items


def _parse_num_token(raw: str) -> float:
    s = (raw or "").strip()
    s = s.replace("，", ",").replace(" ", "")

    if re.fullmatch(r"\d{1,3}[.,]\d{3}(?:[.,]\d{3})*", s):
        s = re.sub(r"[.,]", "", s)
        return float(s)

    s = s.replace(",", "")
    return float(s)


def _extract_candidates_from_items_raw(items, roi_w: int | None = None):
    """
    返回 list[(raw:int, cx_norm:float|None)]
    cx_norm: 0~1，越小越靠左
    """
    out = []

    for it in items:
        t = (it.get("text") or "").strip()
        if not t:
            continue

        # 统一全角/大小写
        s = (t.replace("，", ",")
               .replace("Ｋ", "K").replace("ｋ", "k")
               .replace("Ｗ", "W").replace("ｗ", "w")
               .replace("Ｍ", "M").replace("ｍ", "m")
               .replace("＋", "+"))

        cx = it.get("cx")
        cx_norm = None
        if roi_w and isinstance(cx, (int, float)) and roi_w > 0:
            cx_norm = float(cx) / float(roi_w)

        # 1) 带单位（k/w/万/m）——这是最可靠的（纯币一般会有 K）
        for m in re.finditer(r"([0-9][0-9,\.]*(?:[0-9])?)\s*([kKwW万mM])", s):
            num_raw = m.group(1)
            unit = m.group(2).lower()
            try:
                num = _parse_num_token(num_raw)
            except Exception:
                continue

            if unit in ("w", "万"):
                out.append((int(round(num * 10_000)), cx_norm))
            elif unit == "k":
                out.append((int(round(num * 1_000)), cx_norm))
            elif unit == "m":
                out.append((int(round(num * 1_000_000)), cx_norm))

        # 2) 无单位兜底（形如 647,736）
        m2 = re.search(r"\b([0-9]{1,3}(?:[,\.][0-9]{3}){1,2})\b", s)
        if m2:
            raw_num = m2.group(1)
            # ✅ 如果这个数字后面紧跟 +，大概率是右边那串（券/别的数），直接跳过
            tail = s[m2.end():m2.end()+2]
            if "+" in tail:
                continue
            try:
                n = int(re.sub(r"[,\.\s]", "", raw_num))
                if 100_000 <= n <= 9_999_999:
                    w_approx = int(round(n / 10_000.0))
                    out.append((int(w_approx * 10_000), cx_norm))
            except Exception:
                pass

        # 3) 纯数字兜底（>=4 位）
        for m3 in re.finditer(r"\b([0-9][0-9,\.]{3,})\b", s):
            raw_num = m3.group(1)
            tail = s[m3.end():m3.end()+2]
            if "+" in tail:
                continue
            try:
                n = int(re.sub(r"[,\.\s]", "", raw_num))
                if n <= 200_000:
                    out.append((int(n * 1_000), cx_norm))
            except Exception:
                pass

    return out


def _is_direct_number_image(img: np.ndarray) -> bool:
    h, w = img.shape[:2]
    if w <= 500 and h <= 200:
        return True

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    std = np.std(gray)
    if std < 40:
        return True
    return False


def _pick_leftmost_candidate(cands):
    """
    cands: list[(raw, cx_norm)]
    规则：优先选择最靠左（cx_norm 最小）的候选；没有位置则回退取 raw 最大
    """
    if not cands:
        return None
    with_pos = [(raw, cx) for (raw, cx) in cands if isinstance(cx, (int, float))]
    if with_pos:
        with_pos.sort(key=lambda x: x[1])  # cx 越小越靠左
        return with_pos[0][0]
    return max(raw for (raw, _cx) in cands)


def extract_pure_coin_raw(image_input):
    real_path = resolve_image_path(image_input)
    if not real_path or not os.path.exists(real_path):
        return None

    img = _imread_unicode(real_path)
    if img is None:
        return None

    h, w = img.shape[:2]
    ocr = get_ocr()

    # =========================
    # 情况 1：纯数字小图（rec-only）
    # =========================
    if _is_direct_number_image(img):
        try:
            ocr_num = get_ocr_num()
            big = cv2.resize(img, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)

            gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
            gray = _sharp(gray)

            inv = cv2.bitwise_not(gray)
            _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            _, thr_inv = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            for candidate_img in (gray, inv, thr, thr_inv):
                result = _ocr_rec_only(ocr_num, _to_3ch(candidate_img))
                items = _parse_items_from_result(result)
                cands = _extract_candidates_from_items_raw(items, roi_w=None)
                if cands:
                    # 小图没有“左右两串”问题，直接取 max
                    return max(raw for (raw, _cx) in cands)
        except Exception:
            pass

    # =========================
    # 情况 2：整张截图（ROI）
    # 目标：强制只认左边那串 xxxxK
    # =========================

    # ✅ ROI 收紧：尽量只覆盖左币，不碰右边 “xxxxx+”
    # 多个兜底：分辨率/缩放不同也能覆盖
    roi_boxes = [
        (0.68, 0.00, 0.86, 0.16),  # ⭐ 优先：左币区域（推荐）
        (0.64, 0.00, 0.88, 0.18),  # 兜底：稍大
        (0.60, 0.00, 0.90, 0.20),  # 最后兜底：可能会带到右边，但我们会“选最左”
    ]

    best = None

    for (x1r, y1r, x2r, y2r) in roi_boxes:
        x1 = max(0, int(w * x1r))
        y1 = max(0, int(h * y1r))
        x2 = min(w, int(w * x2r))
        y2 = min(h, int(h * y2r))

        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            continue

        roi_h, roi_w = roi.shape[:2]
        variants = _preprocess_variants(roi)

        for _vname, vimg in variants:
            try:
                result = _ocr_run(ocr, vimg)
            except Exception:
                continue

            items = _parse_items_from_result(result)
            if not items:
                continue

            cands = _extract_candidates_from_items_raw(items, roi_w=roi_w)
            if not cands:
                continue

            # ✅ 核心：只取“最靠左”的候选（避免右边数字抽风）
            cand_raw = _pick_leftmost_candidate(cands)
            if cand_raw is None:
                continue

            # 你也可以加一个“纯币合理范围”防呆（可选）
            # 例如：纯币通常是 K 计数，raw 至少几千到几亿之间
            if cand_raw <= 0:
                continue

            if best is None:
                best = cand_raw
            else:
                # 多 ROI/多预处理：如果都识别到，优先选“更靠左”逻辑已在 cand_raw 内完成
                # 这里取更大/更小都可能不稳定，所以保持：优先选第一次成功的（更贴合 ROI 优先级）
                pass

        if best is not None:
            # ROI 优先级：第一组成功就直接返回（减少抽风概率）
            return best

    return best


def extract_pure_coin_k(image_input):
    raw = extract_pure_coin_raw(image_input)
    if raw is None:
        return None
    try:
        return int(round(int(raw) / 1000.0))
    except Exception:
        return None
