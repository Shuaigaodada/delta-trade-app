# src/services/logs_service.py
import os
import re
import shutil
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from src.config import LOG_DIR, PAGE_SIZE


# ======================
# 基础工具
# ======================
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def list_log_dirs() -> List[str]:
    """返回 logs 目录下的所有日志文件夹名（按时间倒序）"""
    ensure_dir(LOG_DIR)
    dirs = [d for d in os.listdir(LOG_DIR) if os.path.isdir(os.path.join(LOG_DIR, d))]
    dirs.sort(reverse=True)
    return dirs


def dir_to_display_time(dir_name: str) -> str:
    """26-02-07_20-20-13 -> 26-02-07 20:20:13"""
    if "_" in dir_name:
        d, t = dir_name.split("_", 1)
        t = t.replace("-", ":")
        return f"{d} {t}"
    return dir_name


def read_log_text_from_dir(dir_name: str) -> str:
    path = Path(LOG_DIR) / dir_name / "log.txt"
    if not path.exists():
        return "⚠️ 未找到 log.txt"
    return path.read_text(encoding="utf-8")


def get_log_images(dir_name: str) -> Tuple[Optional[str], Optional[str]]:
    """返回 (up.png 路径 or None, down.png 路径 or None)"""
    base = Path(LOG_DIR) / dir_name
    up = base / "up.png"
    down = base / "down.png"
    return (str(up) if up.exists() else None, str(down) if down.exists() else None)


# ======================
# ✅ 新逻辑：解析“本次变化”，统一换算成 w（支持小数）
# 兼容：
#   本次变化：400k
#   本次变化: 123w
#   本次变化：1384.20w
#   本次变化：?  -> None
# 规则：1w = 10k
# ======================
_RE_CHANGE = re.compile(
    r"本次变化(?:\s*[:：])?\s*([0-9]+(?:\.[0-9]+)?)\s*([kKwW])",
    re.IGNORECASE,
)


def parse_change_w_from_log_text(text: str) -> Optional[float]:
    """返回 float(w)，解析不到返回 None"""
    if not text:
        return None
    m = _RE_CHANGE.search(text)
    if not m:
        return None

    num = float(m.group(1))
    unit = (m.group(2) or "").lower()

    if unit == "w":
        return float(num)
    if unit == "k":
        return float(num) / 10.0
    return None


# ======================
# 旧逻辑：解析收益（k）
#（用于兼容旧日志：如果没有“本次变化”，再退回旧公式）
# ======================
_RE_RUN = re.compile(r"已跑纯币为(?:\s*[:：])?\s*([0-9]+)\s*k", re.IGNORECASE)
_RE_RESERVE_VALUE = re.compile(r"预留物品总价值为(?:\s*[:：])?\s*([0-9]+)\s*k", re.IGNORECASE)
_RE_BEFORE = re.compile(r"未结算前总纯(?:\s*[:：])?\s*([0-9]+)\s*k", re.IGNORECASE)
_RE_AFTER = re.compile(r"结算后总纯(?:\s*[:：])?\s*([0-9]+)\s*k", re.IGNORECASE)


def parse_profit_k_from_log_text(text: str) -> Optional[int]:
    """返回 int(k)，解析不到返回 None"""
    if not text:
        return None

    m_run = _RE_RUN.search(text)
    m_reserve = _RE_RESERVE_VALUE.search(text)
    m_before = _RE_BEFORE.search(text)

    # 已跑 + 预留 - 未结算前
    if m_run and m_reserve and m_before:
        return int(m_run.group(1)) + int(m_reserve.group(1)) - int(m_before.group(1))

    # 结算后 - 未结算前
    m_after = _RE_AFTER.search(text)
    if m_after and m_before:
        return int(m_after.group(1)) - int(m_before.group(1))

    return None


def _k_to_w(k: int) -> float:
    """k -> w（1w=10k）"""
    return float(k) / 10.0


def format_profit_w(profit_w: Optional[float]) -> str:
    """首页表格展示：+xxw / -xxw / -（最多两位小数）"""
    if profit_w is None:
        return "-"

    # 显示最多两位小数，但去掉尾随 0
    s = f"{profit_w:.2f}".rstrip("0").rstrip(".")
    if profit_w >= 0:
        return f"+{s}w"
    return f"{s}w"


def parse_profit_w_from_log_text(text: str) -> Optional[float]:
    """
    ✅ 首页统一用 w：
    1) 优先用“本次变化”得到 w（支持小数）
    2) 否则用旧公式得到 k，再换算 w
    """
    w = parse_change_w_from_log_text(text)
    if w is not None:
        return w

    k = parse_profit_k_from_log_text(text)
    if k is None:
        return None
    return _k_to_w(k)


# ======================
# 今日/总计统计（w）
# ======================
def _dir_date_prefix(dir_name: str) -> str:
    """26-02-07_20-20-13 -> 26-02-07"""
    if "_" in dir_name:
        return dir_name.split("_", 1)[0]
    return dir_name


def sum_change_w_today() -> float:
    """汇总今天所有日志的“本次变化/赚了多少”，单位 w"""
    today_prefix = datetime.datetime.now().strftime("%y-%m-%d")
    total_w = 0.0
    for d in list_log_dirs():
        if _dir_date_prefix(d) != today_prefix:
            continue
        text = read_log_text_from_dir(d)
        v = parse_profit_w_from_log_text(text)
        if v is not None:
            total_w += float(v)
    return total_w


def sum_change_w_all() -> float:
    """汇总所有日志的“本次变化/赚了多少”，单位 w"""
    total_w = 0.0
    for d in list_log_dirs():
        text = read_log_text_from_dir(d)
        v = parse_profit_w_from_log_text(text)
        if v is not None:
            total_w += float(v)
    return total_w


# ======================
# 表格元数据（home 表格 2 列：时间 / 本次赚了）
# ======================
def build_log_meta(dirs: List[str]) -> List[Dict]:
    metas = []
    for d in dirs:
        text = read_log_text_from_dir(d)
        profit_w = parse_profit_w_from_log_text(text)
        metas.append(
            {
                "dir": d,
                "time": dir_to_display_time(d),
                "profit_w": profit_w,
                "profit_show": format_profit_w(profit_w),
            }
        )
    return metas


def make_log_rows_from_meta(metas: List[Dict]):
    return [[m["time"], m["profit_show"]] for m in metas]


def make_log_table_meta(limit: int = 20):
    dirs = list_log_dirs()[:limit]
    metas = build_log_meta(dirs)
    rows = make_log_rows_from_meta(metas)
    return rows, metas


def make_log_table_page_meta(page: int, page_size: int = PAGE_SIZE):
    dirs = list_log_dirs()
    total = len(dirs)
    total_pages = max(1, (total + page_size - 1) // page_size)

    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_dirs = dirs[start:end]

    metas = build_log_meta(page_dirs)
    rows = make_log_rows_from_meta(metas)
    info = f"第 {page}/{total_pages} 页，共 {total} 条"
    return rows, metas, info, page


# ======================
# 保存日志（保留）
# ======================
def save_submit_log(
    up_img_path: Optional[str],
    down_img_path: Optional[str],
    log_text: str,
    remark: str = "",
    logs_dir: str = LOG_DIR,
) -> str:
    base = Path(logs_dir)
    base.mkdir(parents=True, exist_ok=True)

    folder_name = datetime.datetime.now().strftime("%y-%m-%d_%H-%M-%S")
    out_dir = base / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    if up_img_path:
        shutil.copy2(up_img_path, out_dir / "up.png")
    if down_img_path:
        shutil.copy2(down_img_path, out_dir / "down.png")

    final_log = log_text.rstrip() + "\n"
    final_log += f"\n备注: {remark.strip()}\n"
    (out_dir / "log.txt").write_text(final_log, encoding="utf-8")

    return str(out_dir)
