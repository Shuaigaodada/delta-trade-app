import json
import random
from pathlib import Path

import gradio as gr

from src.services import request_service, logs_service


def format_reserve_text(reserve_dict: dict) -> str:
    if not reserve_dict:
        return "无"
    return ", ".join([f"{k}x{v}" for k, v in reserve_dict.items()])


_FINANCE_FILE = Path("data") / "finance.json"


def _read_prepayment_total() -> float:
    if not _FINANCE_FILE.exists():
        return 0.0
    try:
        obj = json.loads(_FINANCE_FILE.read_text(encoding="utf-8"))
        total = obj.get("prepayment", {}).get("total", 0)
        return float(total or 0)
    except Exception:
        return 0.0


def _money_map() -> dict:
    arr = request_service.get_person_money()
    mp = {}
    for x in arr or []:
        try:
            item_id = str(x.get("item", "")).strip()
            total = int(str(x.get("totalMoney", "0")).strip() or "0")
            if item_id:
                mp[item_id] = total
        except Exception:
            continue
    return mp


def _to_w_show(v) -> str:
    try:
        n = int(v)
    except Exception:
        return "-"

    if abs(n) >= 10000:
        return f"{round(n / 10000)}w"
    return str(n)


def _fmt_w2(x) -> str:
    try:
        v = float(x)
    except Exception:
        return "0"
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s


def home_stats_text() -> str:
    prepayment_total = _read_prepayment_total()

    mp = _money_map()
    hav = mp.get("17020000010")       # 哈夫币
    ticket = mp.get("17888808889")    # 三角券
    coin = mp.get("17888808888")      # 三角币

    hav_s = _to_w_show(hav)
    ticket_s = _to_w_show(ticket)
    coin_s = _to_w_show(coin)

    # 今日/总计（单位 w，支持小数）
    try:
        today_w = float(logs_service.sum_change_w_today() or 0)
    except Exception:
        today_w = 0.0

    try:
        all_w = float(logs_service.sum_change_w_all() or 0)
    except Exception:
        all_w = 0.0

    suffix = ""
    if today_w >= 3000:
        suffix = random.choice([
            "（卧槽知神！！！）",
            "（去交易行抢钱了？）",
            "（妈妈！）",
            "（跑刀界的王！）",
            "（跑刀界的神！）",
            "（膜拜知神）",
        ])

    return (
        f"当前预付款: {_fmt_w2(prepayment_total)}元\n"
        f"当前账号哈夫币: {hav_s}\n"
        f"当前账号三角券: {ticket_s}\n"
        f"当前账号三角币: {coin_s}\n"
        f"知更大人今日已跑: {_fmt_w2(today_w)}w{suffix}\n"
        f"知更大人总共为糕神跑了: {_fmt_w2(all_w)}w"
    )


def show_pages(p1, p2, p3, p4, p5, p6, p7):
    return (
        gr.update(visible=p1),
        gr.update(visible=p2),
        gr.update(visible=p3),
        gr.update(visible=p4),
        gr.update(visible=p5),
        gr.update(visible=p6),
        gr.update(visible=p7),
    )
