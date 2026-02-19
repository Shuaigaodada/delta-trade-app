# src/ui/pages/reserve_manager.py
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import gradio as gr

from src.services import request_service

# ========= 持久化文件 =========
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
MANUAL_PRICE_FILE = DATA_DIR / "manual_prices.json"
FRAMEWORK_TOKEN_FILE = DATA_DIR / "frameworkToken"

def _read_framework_token() -> str:
    try:
        return FRAMEWORK_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

def _save_framework_token(token: str) -> None:
    t = (token or "").strip()
    FRAMEWORK_TOKEN_FILE.write_text(t, encoding="utf-8")
    # 让 request_service 立刻可用（可选，但建议做）
    try:
        request_service.write_framework_token(t)
    except Exception:
        # 就算这里失败，get_person_money 也会 read_framework_token() 从文件读
        pass



def _load_manual_prices() -> Dict[str, int]:
    if not MANUAL_PRICE_FILE.exists():
        return {}
    try:
        obj = json.loads(MANUAL_PRICE_FILE.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            out: Dict[str, int] = {}
            for k, v in obj.items():
                if isinstance(k, str):
                    try:
                        out[k.strip()] = int(v)
                    except Exception:
                        continue
            return out
    except Exception:
        return {}
    return {}


def _save_manual_prices(prices: Dict[str, int]) -> None:
    MANUAL_PRICE_FILE.write_text(
        json.dumps(prices, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ========= 价格解析：支持 k/w =========
# 例：
# 100k -> 100000
# 2.5k -> 2500
# 100w -> 1000000
# 1.2w -> 12000
_PRICE_TOKEN_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKwW])?\s*$")


def parse_price_token(s: str) -> int:
    """
    支持：纯数字 / 数字+k / 数字+w（k=1e3, w=1e4）
    返回：raw 整数
    """
    s = (s or "").strip().replace(",", "")
    m = _PRICE_TOKEN_RE.match(s)
    if not m:
        raise ValueError(f"价格格式不支持：{s}（示例：12345 / 100k / 100w / 2.5k / 1.2w）")
    num = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit == "k":
        num *= 1000
    elif unit == "w":
        num *= 10000
    return int(round(num))


# ==== 价格展示：优先 w，其次 k，否则原数字 ====
# 你要求：1253156 -> 125w（即按万为单位四舍五入到整数）
def _format_price_human(raw: int) -> str:
    try:
        v = int(raw)
    except Exception:
        return str(raw)

    if v == 0:
        return "0"

    # >= 1w：四舍五入到整数 w（1253156 -> 125w）
    if abs(v) >= 10000:
        return f"{int(round(v / 10000.0))}w"

    # >= 1k：四舍五入到整数 k
    if abs(v) >= 1000:
        return f"{int(round(v / 1000.0))}k"

    return str(v)


def _normalize_separators(s: str) -> str:
    return (
        (s or "")
        .replace("，", ",")
        .replace("；", ",")
        .replace(";", ",")
        .replace("、", ",")
        .replace("\n", ",")
        .strip()
    )


def _parse_input(text: str) -> List[Tuple[str, int]]:
    """
    必须：物品名x数量, 物品名x数量
    x 支持：x / X / × / *
    """
    if not text or not text.strip():
        raise ValueError("请输入：物品名x数量, 物品名x数量")

    s = _normalize_separators(text)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        raise ValueError("请输入：物品名x数量, 物品名x数量")

    out: List[Tuple[str, int]] = []
    for p in parts:
        m = re.match(r"^(?P<name>.+?)\s*[xX×\*]\s*(?P<qty>\d+)\s*$", p)
        if not m:
            raise ValueError(f"格式错误：`{p}`\n正确示例：非洲之心x2, 留声机x1")
        name = (m.group("name") or "").strip()
        qty = int(m.group("qty") or 1)

        if not name:
            raise ValueError(f"物品名不能为空：`{p}`")
        if qty <= 0:
            raise ValueError(f"数量必须为正整数：`{p}`")
        out.append((name, qty))

    return out


def _search_first_item(name: str) -> Dict[str, Any]:
    results = request_service.search_item(name)
    if not results:
        return {"name": name, "ok": False, "reason": "未搜索到结果"}

    first = results[0]
    return {
        "name": name,
        "ok": True,
        "objectName": first.get("objectName", name),
        "objectID": int(first.get("objectID")),
        "searchAvgPrice": int(first.get("avgPrice", 0) or 0),
    }


def calc_from_text(input_text: str) -> str:
    """
    输出到可编辑文本框：每行 “物品名 x数量 单价: 125w”
    你要求：
      - 显示统一用 w/k（如 1253156 -> 125w）
      - 不要 {p:xxx}
      - 不要（✅ 使用官方最新均价）之类提示
    """
    try:
        pairs = _parse_input(input_text)
    except Exception as e:
        return f"❌ 输入解析失败：{e}"

    manual_prices = _load_manual_prices()

    # 1) 并发搜索
    max_workers = min(8, max(1, len(pairs)))
    tmp: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_map = {ex.submit(_search_first_item, name): (name, qty) for name, qty in pairs}
        for fut in as_completed(fut_map):
            name, qty = fut_map[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"name": name, "ok": False, "reason": f"搜索异常：{e}"}
            r["qty"] = qty
            tmp.append(r)

    # 保持输入顺序（注意：同名会覆盖排序键；如要支持同名重复可再扩展）
    order = {name: i for i, (name, _) in enumerate(pairs)}
    tmp.sort(key=lambda x: order.get(x["name"], 999999))

    ok_items = [x for x in tmp if x.get("ok")]
    object_ids = [x["objectID"] for x in ok_items]

    # 2) 批量拿最新均价
    latest_map: Dict[str, Dict[str, Any]] = {}
    if object_ids:
        try:
            latest_map = request_service.get_latest_price(object_ids) or {}
        except Exception:
            latest_map = {}

    def _get_latest_price_positive(oid_str: str) -> Optional[int]:
        """从 latest_map 取 avgPrice，且必须 >0 才算有效"""
        v = latest_map.get(oid_str)
        if isinstance(v, dict) and "avgPrice" in v:
            try:
                p = int(v["avgPrice"] or 0)
                return p if p > 0 else None
            except Exception:
                return None
        return None

    lines: List[str] = []

    for x in tmp:
        raw_name = x["name"]
        qty = int(x.get("qty", 0) or 0)
        manual = manual_prices.get(raw_name)  # 只按“输入名”匹配

        # --- A) 搜不到：优先微调价 ---
        if not x.get("ok"):
            unit_price = int(manual) if manual is not None else 0
            show_p = _format_price_human(unit_price)
            # 失败情况保留原因（不带 ✅ 文案）
            if manual is not None:
                lines.append(f"{raw_name} x{qty} 单价: {show_p}")
            else:
                lines.append(f"{raw_name} x{qty} 单价: 0（{x.get('reason', '未搜索到结果')}）")
            continue

        obj_name = x.get("objectName", raw_name)
        oid = str(x["objectID"])
        search_price = int(x.get("searchAvgPrice", 0) or 0)

        # --- B) 搜得到但 avgPrice==0：优先微调价 ---
        if search_price <= 0:
            if manual is not None:
                unit_price = int(manual)
                show_p = _format_price_human(unit_price)
                lines.append(f"{obj_name} x{qty} 单价: {show_p}")
            else:
                lines.append(f"{obj_name} x{qty} 单价: 0")
            continue

        # --- C) 搜得到且 search_price>0：优先“最新均价(>0)” -> “搜索价(>0)” ---
        latest_price = _get_latest_price_positive(oid)
        unit_price = int(latest_price) if latest_price is not None else int(search_price)

        show_p = _format_price_human(unit_price)
        lines.append(f"{obj_name} x{qty} 单价: {show_p}")

    lines.append("")
    lines.append(
        "提示：你可以直接在本框内手动修改单价/总计（用于微调）。单价支持 k/w：100k=100000，100w=1000000。修改完成后点击确定，最终总计会显示在结算页，并写入本地缓存。"
    )

    return "\n".join(lines)


# ======== 解析结果框（允许备注 + 允许 k/w） ========
# 支持：
# 物品 x2 单价: 125w
# 物品 x1 单价: 198k
# 物品 x1 单价: 12345
_PRICE_LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<name>.+?)                  # 名称
    \s*[xX×\*]\s*(?P<qty>\d+)      # 必须有数量
    \s+单价\s*[:：]\s*
    (?P<price>[0-9.,]+(?:\.[0-9]+)?[kKwW]?)   # 允许 33w 125k 12345
    \s*$
    """,
    re.VERBOSE,
)

_TOTAL_RE = re.compile(r"^\s*总计\s*[:：]\s*(?P<total>[0-9.,]+(?:\.[0-9]+)?\s*[kKwW]?)\s*$")


def _extract_items_and_total(result_text: str) -> Tuple[List[Tuple[str, str, int, int]], Optional[int]]:
    """
    返回：
      [(display_name, raw_name, unit_price_raw, qty), ...], total_from_line
    注意：此处 unit_price_raw 来自用户编辑后的 price（如 125w -> 1250000）
    """
    items: List[Tuple[str, str, int, int]] = []
    total_from_line: Optional[int] = None

    for raw in (result_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        m_total = _TOTAL_RE.match(line)
        if m_total:
            try:
                total_from_line = parse_price_token(m_total.group("total"))
            except Exception:
                total_from_line = None
            continue

        m = _PRICE_LINE_RE.match(line)
        if not m:
            continue

        display_name = (m.group("name") or "").strip()
        qty = int(m.group("qty") or 1)
        raw_name = ((m.groupdict().get("raw") or display_name) or "").strip()

        price_raw = (m.group("price") or "").strip()

        print(f"解析行：{line} -> display_name={display_name}, raw_name={raw_name}, price_raw={price_raw}, qty={qty}")
        try:
            unit_price = parse_price_token(price_raw)
        except Exception:
            unit_price = 0

        if display_name:
            items.append((display_name, raw_name, int(unit_price), int(qty)))

    return items, total_from_line


def apply_prices_and_build_summary(result_text: str) -> str:
    """
    点击“确定”时调用：
    1) 从 result_box 解析物品单价（支持 k/w、支持数量）
    2) 写入 data/manual_prices.json（下次 calc_from_text 会优先使用）
    3) 返回结算页显示文案： raw(物品名)*数量 + ... = 总raw
    """
    if not result_text:
        return "无"

    items, total_from_line = _extract_items_and_total(result_text)
    if not items and total_from_line is None:
        return "无"

    # 保存微调价：保存“单价”（不是小计）
    manual_prices = _load_manual_prices()
    for display_name, raw_name, unit_price, qty in items:
        unit_price = int(unit_price)
        if raw_name:
            manual_prices[raw_name] = unit_price
        if display_name:
            manual_prices[display_name] = unit_price
    _save_manual_prices(manual_prices)

    # 总价按：单价*数量
    sum_subtotals = sum(int(unit_price) * int(qty) for _d, _r, unit_price, qty in items)
    total = total_from_line if total_from_line is not None else sum_subtotals

    # 结算页表达式：raw(名)*数量
    expr = " + ".join([f"{unit_price}({display})*{qty}" for display, _raw, unit_price, qty in items])

    if expr:
        return f"{expr} = {int(total)}"
    return f"= {int(total)}"


# ====== 最终对外接口（page.py 只认这个） ======
def build_settlement_summary(result_text: str) -> str:
    return apply_prices_and_build_summary(result_text)


def build():
    with gr.Group(visible=False) as page:
        gr.HTML("<div class='panel'><div class='title'>管理预留物品</div></div>")

        input_box = gr.Textbox(
            label="预留物品输入（必须：物品名x数量, 物品名x数量）",
            placeholder="示例：非洲之心x2, 留声机x1",
            lines=2,
        )

        with gr.Row(elem_classes=["center-btn"]):
            btn_confirm = gr.Button("确认计算", variant="primary")

        result_box = gr.Textbox(
            label="计算结果（可手动修改）",
            value="",
            lines=16,
            interactive=True,
            elem_classes=["panel"],
        )

        with gr.Row(elem_classes=["center-btn"]):
            btn_apply = gr.Button("确定", variant="primary")

        with gr.Row(elem_classes=["center-btn"]):
            btn_mgr_back = gr.Button("返回结算页")

    widgets = {
        "input_box": input_box,
        "btn_confirm": btn_confirm,
        "result_box": result_box,
        "btn_apply": btn_apply,
        "btn_mgr_back": btn_mgr_back,
    }
    return page, widgets


# =========================
# Confirm 页：把结算页表达式解析成 “名x数量(125w)” + “总计: 4800w”
# =========================

_SUM_ITEM_RE = re.compile(r"(?P<price>\d+)\((?P<name>[^)]+)\)(?:\*(?P<qty>\d+))?")
_SUM_TOTAL_EQ_RE = re.compile(r"=\s*(?P<total>\d+)\s*$")
_SUM_TOTAL_K_RE = re.compile(r"总计\s*[:：]\s*(?P<num>\d+)\s*(?P<unit>[kKwW]?)")


def parse_settlement_reserve_text(reserve_text: str) -> Tuple[List[Tuple[str, int, int]], int]:
    """
    从结算页 reserve_total_text 解析出：
      - [(name, qty, unit_price_raw), ...]
      - total_raw（raw单位整数）
    """
    if not reserve_text:
        return [], 0

    s = reserve_text.strip()
    if s in ("无", "（无预留物品）"):
        return [], 0

    # 兜底：如果有 “总计: xxxk/xxxw”
    m = _SUM_TOTAL_K_RE.search(s)
    if m:
        num = int(m.group("num"))
        unit = (m.group("unit") or "").lower()
        if unit == "w":
            return [], num * 10000
        if unit == "k":
            return [], num * 1000
        return [], num

    # 主解析：price(name)*qty
    items: List[Tuple[str, int, int]] = []
    for mm in _SUM_ITEM_RE.finditer(s):
        name = (mm.group("name") or "").strip()
        if not name:
            continue
        unit_price = int(mm.group("price") or 0)
        qty = int(mm.group("qty") or 1)
        items.append((name, qty, unit_price))

    # 总计：取 '=' 后面的数字（raw）
    total_raw = 0
    m2 = _SUM_TOTAL_EQ_RE.search(s)
    if m2:
        total_raw = int(m2.group("total"))
    else:
        total_raw = sum(unit_price * qty for _, qty, unit_price in items)

    return items, total_raw


def build_confirm_reserve_line(reserve_text: str) -> Tuple[str, int]:
    """
    返回：
      - "预留物品: 名x数量(125w), ... 总计: 4800w"
      - total_raw（raw单位）
    """
    items, total_raw = parse_settlement_reserve_text(reserve_text)

    if not items and total_raw == 0:
        return "预留物品: 无 总计: 0", 0

    parts = []
    for name, qty, unit_price in items:
        parts.append(f"{name}x{qty}({_format_price_human(unit_price)})")

    total_show = _format_price_human(total_raw)
    if parts:
        return f"预留物品: {', '.join(parts)} 总计: {total_show}", total_raw

    return f"预留物品: （未列出名称） 总计: {total_show}", total_raw
