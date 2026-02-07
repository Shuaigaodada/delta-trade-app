import os
import re
from src.config import LOG_DIR, PAGE_SIZE


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def list_log_files():
    ensure_dir(LOG_DIR)
    files = [fn for fn in os.listdir(LOG_DIR) if fn.lower().endswith(".txt")]
    files.sort(reverse=True)
    return files


def filename_to_display_time(fn: str):
    base = fn[:-4]
    if "_" in base:
        d, t = base.split("_", 1)
        t = t.replace("-", ":")
        return f"{d} {t}"
    return base


def read_log_file_by_filename(fn: str):
    path = os.path.join(LOG_DIR, fn)
    if not os.path.exists(path):
        return f"⚠️ 找不到日志文件：{path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# =========================================================
# 解析“本次赚了多少”
#
# 优先使用你要求的公式：
#   本次赚(k) = 已跑纯币 + 预留物品总价值 - 未结算前总纯
#
# 解析不到则 fallback：
#   本次赚(k) = 结算后总纯 - 未结算前总纯
# =========================================================

# ✅ 冒号可选（你的日志是“已跑纯币为8884k”，没有冒号）
_RE_RUN = re.compile(r"已跑纯币为(?:\s*[:：])?\s*([0-9]+)\s*k", re.IGNORECASE)

# 这些一般带冒号，但也做成可选更稳
_RE_RESERVE_VALUE = re.compile(r"预留物品总价值为(?:\s*[:：])?\s*([0-9]+)\s*k", re.IGNORECASE)
_RE_BEFORE = re.compile(r"未结算前总纯(?:\s*[:：])?\s*([0-9]+)\s*k", re.IGNORECASE)
_RE_AFTER = re.compile(r"结算后总纯(?:\s*[:：])?\s*([0-9]+)\s*k", re.IGNORECASE)


def parse_profit_k_from_log_text(text: str):
    """
    返回 int（单位k），解析不到返回 None
    """
    if not text:
        return None

    m_run = _RE_RUN.search(text)
    m_reserve = _RE_RESERVE_VALUE.search(text)
    m_before = _RE_BEFORE.search(text)

    # ===== 优先：已跑 + 预留价值 - 未结算前 =====
    if m_run and m_reserve and m_before:
        run_k = int(m_run.group(1))
        reserve_k = int(m_reserve.group(1))
        before_k = int(m_before.group(1))
        return run_k + reserve_k - before_k

    # ===== fallback：结算后 - 未结算前 =====
    m_after = _RE_AFTER.search(text)
    if m_after and m_before:
        after_k = int(m_after.group(1))
        before_k = int(m_before.group(1))
        return after_k - before_k

    return None


def format_profit_k(profit_k):
    if profit_k is None:
        return "-"
    if profit_k >= 0:
        return f"+{profit_k}k"
    return f"{profit_k}k"


def build_log_meta(files):
    metas = []
    for fn in files:
        try:
            text = read_log_file_by_filename(fn)
        except Exception:
            text = ""

        profit_k = parse_profit_k_from_log_text(text)
        metas.append(
            {
                "file": fn,
                "time": filename_to_display_time(fn),
                "profit_k": profit_k,
                "profit_show": format_profit_k(profit_k),
            }
        )
    return metas


def make_log_rows_from_meta(metas):
    return [[m["time"], "查看详情", m["profit_show"]] for m in metas]


def make_log_table_meta(limit=20):
    files = list_log_files()[:limit]
    metas = build_log_meta(files)
    rows = make_log_rows_from_meta(metas)
    return rows, metas


def make_log_table_page_meta(page: int, page_size: int = PAGE_SIZE):
    files = list_log_files()
    total = len(files)
    total_pages = max(1, (total + page_size - 1) // page_size)

    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_files = files[start:end]

    metas = build_log_meta(page_files)
    rows = make_log_rows_from_meta(metas)

    info = f"第 {page}/{total_pages} 页，共 {total} 条"
    return rows, metas, info, page


# ===== 兼容旧接口（如果别处还在用）=====
def make_log_table(limit=20):
    rows, _ = make_log_table_meta(limit)
    return rows


def make_log_table_page(page: int, page_size: int = PAGE_SIZE):
    rows, _, info, page = make_log_table_page_meta(page, page_size)
    return rows, info, page
