# src/utils/money_format.py
from __future__ import annotations

import re
from typing import Optional, Union

Number = Union[int, float, str]

# 你项目的特殊写法：A e B w 代表 A亿 + B万
# 例：1e3000w = 1亿 + 3000万 = 130,000,000
_RE_YI_WAN = re.compile(r"^\s*(\d+)\s*[eE]\s*(\d+)\s*[wW]\s*$")

# 常规：123 / 3.2w / 2323k / 123m / 123,456
_RE_UNIT = re.compile(r"^\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmMwW]?)\s*$")


def parse_money_token(s: str) -> int:
    """
    解析输入为 raw 整数（基础单位：1）：
      - 3.2w -> 32000
      - 50w -> 500000
      - 2323k -> 2323000
      - 123m -> 123000000
      - 1e3000w -> 130000000 （1亿 + 3000万）
      - 123,456 -> 123456
    """
    s = (s or "").strip()
    if not s:
        raise ValueError("empty money token")

    # A e B w：A亿 + B万
    m = _RE_YI_WAN.match(s)
    if m:
        yi = int(m.group(1))
        wan = int(m.group(2))
        return yi * 100_000_000 + wan * 10_000

    # 常规单位
    s2 = s.replace("，", ",")
    m2 = _RE_UNIT.match(s2)
    if not m2:
        raise ValueError(f"unsupported money token: {s}")

    num = float(m2.group(1).replace(",", ""))
    unit = (m2.group(2) or "").lower()

    if unit == "k":
        num *= 1_000
    elif unit == "w":
        num *= 10_000
    elif unit == "m":
        num *= 1_000_000

    return int(round(num))


def _trim_float(x: float, max_decimals: int = 1) -> str:
    s = f"{x:.{max_decimals}f}".rstrip("0").rstrip(".")
    return s if s else "0"


def format_money(raw: Optional[int]) -> str:
    """
    你项目的显示规则：
      - < 1e8：统一用 w（允许 1 位小数，如 3.2w）
      - >= 1e8：用 A e B w（A亿 + B万）
    """
    if raw is None:
        return "-"

    try:
        n = int(raw)
    except Exception:
        return str(raw)

    sign = "-" if n < 0 else ""
    n = abs(n)

    if n == 0:
        return "0"

    # < 1亿：统一 w
    if n < 100_000_000:
        w = n / 10_000.0
        return f"{sign}{_trim_float(w, 1)}w"

    # >= 1亿：A亿 + B万（B 取整万）
    yi = n // 100_000_000
    rem = n - yi * 100_000_000
    wan = rem // 10_000

    # 正常不会溢出，这里加个保险
    if wan >= 10_000:
        yi += wan // 10_000
        wan %= 10_000

    return f"{sign}{yi}e{wan}w"


def format_money_from_k(k: Optional[int]) -> str:
    """
    OCR/日志里如果拿到的是 k（千），转成 raw 再按你项目规则显示
    """
    if k is None:
        return "-"
    return format_money(int(k) * 1000)
