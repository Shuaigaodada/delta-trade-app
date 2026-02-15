import json
import random
from pathlib import Path

import gradio as gr

from src.services import request_service, logs_service
from src.utils.money_format import format_money


def format_reserve_text(reserve_dict: dict) -> str:
    if not reserve_dict:
        return "无"
    return ", ".join([f"{k}x{v}" for k, v in reserve_dict.items()])


_FINANCE_FILE = Path("data") / "finance.json"

# ✅ 语音目录
_EGG_AUDIO_DIR = Path("static/egg_audio")


def list_egg_audio_paths() -> list[str]:
    if not _EGG_AUDIO_DIR.exists():
        return []
    return [p.as_posix() for p in sorted(_EGG_AUDIO_DIR.glob("*.m4a"))]


def pick_random_egg_audio_path() -> str | None:
    files = list_egg_audio_paths()
    if not files:
        return None
    return random.choice(files)


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


def _fmt_yuan(x) -> str:
    try:
        v = float(x)
    except Exception:
        return "0"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def home_stats_text() -> str:
    prepayment_total = _read_prepayment_total()

    mp = _money_map()
    hav = mp.get("17020000010")       # 哈夫币
    ticket = mp.get("17888808889")    # 三角券
    coin = mp.get("17888808888")      # 三角币

    hav_s = format_money(hav)
    ticket_s = format_money(ticket)
    coin_s = format_money(coin)

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

    today_s = format_money(int(round(today_w * 10_000)))
    all_s = format_money(int(round(all_w * 10_000)))

    return (
        f"当前预付款: {_fmt_yuan(prepayment_total)}元\n"
        f"当前账号哈夫币: {hav_s}\n"
        f"当前账号三角券: {ticket_s}\n"
        f"当前账号三角币: {coin_s}\n"
        f"知更大人今日已跑: {today_s}{suffix}\n"
        f"知更大人总共为糕神跑了: {all_s}"
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
