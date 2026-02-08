# src/services/finance_service.py
import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

FINANCE_FILE = Path("data/finance.json")


def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _ensure_shape(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}

    pre = data.get("prepayment")
    if not isinstance(pre, dict):
        pre = {}

    if "total" not in pre:
        pre["total"] = 0

    if not isinstance(pre.get("add_log"), dict):
        pre["add_log"] = {}

    if not isinstance(pre.get("deduct_log"), dict):
        pre["deduct_log"] = {}

    data["prepayment"] = pre
    return data


def load_finance() -> Dict[str, Any]:
    if not FINANCE_FILE.exists():
        return _ensure_shape({})
    try:
        obj = json.loads(FINANCE_FILE.read_text(encoding="utf-8"))
        return _ensure_shape(obj)
    except Exception:
        return _ensure_shape({})


def save_finance(data: Dict[str, Any]) -> None:
    data = _ensure_shape(data)
    FINANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    FINANCE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_prepayment_total() -> float:
    data = load_finance()
    return _safe_float(data["prepayment"].get("total", 0), 0.0)


def deduct_prepayment(amount_yuan: float, ts: Optional[str] = None) -> Dict[str, Any]:
    """
    ✅ 新规则：允许扣到负数（欠款）
      total -= amount_yuan（amount_yuan <=0 则不扣）
      deduct_log[ts] = amount_yuan（两位小数）
    """
    data = load_finance()
    pre = data["prepayment"]

    total = _safe_float(pre.get("total", 0), 0.0)
    deduct = max(0.0, _safe_float(amount_yuan, 0.0))  # 防止传负数把余额加回去

    remain = total - deduct  # ✅ 允许 remain 为负数
    pre["total"] = round(remain, 2)

    if deduct > 0:
        if not ts:
            ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
        pre["deduct_log"][ts] = round(deduct, 2)

    data["prepayment"] = pre
    save_finance(data)
    return {"deduct": round(deduct, 2), "remain": round(remain, 2)}


def admin_set_prepayment_total(new_total_yuan: float, ts: Optional[str] = None) -> Dict[str, Any]:
    """
    ✅ 管理员：直接设置预付款余额（可负数）
    - total = new_total
    - add_log[ts] = delta（新-旧），保留两位小数
    """
    data = load_finance()
    pre = data["prepayment"]

    old_total = _safe_float(pre.get("total", 0), 0.0)
    new_total = _safe_float(new_total_yuan, old_total)

    delta = new_total - old_total
    pre["total"] = round(new_total, 2)

    if abs(delta) > 1e-9:
        if not ts:
            ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
        pre["add_log"][ts] = round(delta, 2)

    data["prepayment"] = pre
    save_finance(data)
    return {
        "old": round(old_total, 2),
        "new": round(new_total, 2),
        "delta": round(delta, 2),
    }
