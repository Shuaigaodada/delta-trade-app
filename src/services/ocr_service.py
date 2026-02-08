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

    try:
        if not isinstance(result, list) or not result:
            return texts

        # PaddleOCR 通常是按页返回：result[0] 是第一页
        page = result[0]

        # 情况 A：rec-only 可能返回：[[(' 647,736', 0.87)]]
        # 或 [[[' 647,736', 0.87]]]（有些版本会更“嵌套”）
        if isinstance(page, list) and page:
            for item in page:
                # item = ('text', score)
                if isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], str):
                    text = item[0]
                    score = item[1]
                    try:
                        if float(score) >= 0.08:
                            texts.append(text)
                    except Exception:
                        texts.append(text)
                    continue

                # 情况 B：经典 det+rec：item = [box, (text, score)]
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    ts = item[1]
                    if isinstance(ts, (list, tuple)) and len(ts) >= 1 and isinstance(ts[0], str):
                        text = ts[0]
                        score = ts[1] if len(ts) > 1 else 1.0
                        if float(score) >= 0.08:
                            texts.append(text)

            if texts:
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


def _parse_num_token(raw: str) -> float:
    """
    解析数字 token，兼容：
    - 21,789  (千分位)
    - 21.789  (有些 OCR 会把千分位逗号识别成点；这里要当千分位而不是小数)
    - 64.7 / 64,7 (小数)
    """
    s = (raw or "").strip()
    s = s.replace("，", ",").replace(" ", "")

    # 关键：如果是 1~3 位 + [.,] + 3 位（典型千分位），把分隔符当千分位
    # 例：21.789 -> 21789
    if re.fullmatch(r"\d{1,3}[.,]\d{3}(?:[.,]\d{3})*", s):
        s = re.sub(r"[.,]", "", s)
        return float(s)

    # 正常：逗号视为千分位，点视为小数点
    s = s.replace(",", "")
    return float(s)


def _extract_candidates_from_texts(texts):
    """
    返回单位：k（整数）

    兼容：
    - 21,789k / 21.789k  -> 21789k
    - 2.1w / 2.1万       -> 21000k
    - 647,736（无单位的小截图）-> 约 64k（按你的需求做兼容）
    """
    candidates_k = []

    for t in texts:
        s = (t or "").strip()
        if not s:
            continue

        s = s.replace("，", ",").replace("Ｋ", "K").replace("ｋ", "k").replace("Ｗ", "W").replace("ｗ", "w")

        # 1) 带单位（k/w/万）
        for m in re.finditer(r"([0-9][0-9,\.]*(?:[0-9])?)\s*([kKwW万])", s):
            num_raw = m.group(1)
            unit = m.group(2).lower()
            try:
                num = _parse_num_token(num_raw)
            except Exception:
                continue

            if unit in ("w", "万"):
                # w=万，换算到 k：1w = 10k
                candidates_k.append(int(round(num * 10_000 / 1000)))  # num*10000(原始) /1000 = k
            else:
                # k：就是 k
                candidates_k.append(int(round(num)))

        # 2) 无单位兜底（你这种小截图：647,736 期望≈64k）
        # 规则：无单位且像“xxx,xxx”这种 6 位数字，按 /10000 得到 k（你给的期望）
        # 647,736 -> 647736/10000=64.7736 -> 65k
        m2 = re.search(r"\b([0-9]{1,3}(?:[,\.][0-9]{3}){1,2})\b", s)
        if m2:
            raw = m2.group(1)
            try:
                n = int(re.sub(r"[,\.\s]", "", raw))
                # 只对“看起来像 6~7 位的大数”做这个兼容，避免误伤
                if 100_000 <= n <= 9_999_999:
                    candidates_k.append(int(round(n / 10_000.0)))
            except Exception:
                pass

        # 3) 纯数字兜底（最后保底：>=4 位）
        for m3 in re.finditer(r"\b([0-9][0-9,\.]{3,})\b", s):
            raw = m3.group(1)
            try:
                n = int(re.sub(r"[,\.\s]", "", raw))
                # 如果是特别大的数，别当 k（避免把原始金币当 k）
                if n <= 200_000:  # 你业务里 k 通常不会太离谱，可按你实际再调
                    candidates_k.append(n)
            except Exception:
                pass

    return candidates_k



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

def _is_direct_number_image(img: np.ndarray) -> bool:
    """
    判断是否为“已经裁好的纯数字截图”
    比如：647,736 / 21,789K
    """
    h, w = img.shape[:2]

    # ① 尺寸很小：大概率是手动裁过的数字图
    if w <= 500 and h <= 200:
        return True

    # ② 颜色简单（黑底白字 / 深底亮字）
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    std = np.std(gray)

    # 纹理很少，说明不是复杂 UI
    if std < 40:
        return True

    return False


def extract_pure_coin_k(image_input):
    real_path = resolve_image_path(image_input)
    if not real_path or not os.path.exists(real_path):
        return None

    img = _imread_unicode(real_path)
    if img is None:
        return None

    h, w = img.shape[:2]
    ocr = get_ocr()

    # =========================
    # ✅ 情况 1：纯数字小图，优先走“数字专用 OCR”（rec-only）
    # =========================
    if _is_direct_number_image(img):
        try:
            ocr_num = get_ocr_num()

            # 放大（rec-only 对分辨率敏感）
            big = cv2.resize(img, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)

            gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
            gray = _sharp(gray)

            # 黑底白字：反色
            inv = cv2.bitwise_not(gray)

            # 再做一次 Otsu 二值（有些数字边缘更稳）
            _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            _, thr_inv = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            for candidate_img in (gray, inv, thr, thr_inv):
                result = _ocr_rec_only(ocr_num, _to_3ch(candidate_img))
                texts = _parse_texts_from_result(result)

                candidates = _extract_candidates_from_texts(texts)
                if candidates:
                    return max(candidates)
        except Exception:
            pass
    # 如果小图 rec-only 也失败，继续走 ROI 兜底


    # =========================
    # 情况 2：整张游戏截图，裁 ROI
    # =========================
    roi_boxes = [
        (0.52, 0.00, 0.80, 0.18),
        (0.48, 0.00, 0.86, 0.22),
        (0.55, 0.00, 1.00, 0.22),
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

        variants = _preprocess_variants(roi)

        for _, vimg in variants:
            try:
                result = _ocr_run(ocr, vimg)
            except Exception:
                continue

            texts = _parse_texts_from_result(result)
            if not texts:
                continue

            candidates = _extract_candidates_from_texts(texts)
            if candidates:
                cand = max(candidates)
                if best is None or cand > best:
                    best = cand

    return best
