import gradio as gr
from src.services.request_service import search_item
from src.ui.pages.common import format_reserve_text


def build_search_gallery(results: list[dict]):
    gallery = []
    for x in results or []:
        name = x.get("objectName", "")
        oid = x.get("objectID", "")
        pic = x.get("pic", None)
        price = x.get("avgPrice", None)
        caption = f"{name} ({oid})\n{price}"
        gallery.append((pic, caption))
    return gallery


def build_dropdown_choices(results: list[dict]):
    choices = []
    for x in results or []:
        name = x.get("objectName", "")
        oid = x.get("objectID", "")
        if name and oid:
            choices.append(f"{name} ({oid})")
    return choices


def on_search_confirm(keyword: str):
    kw = (keyword or "").strip()
    if not kw:
        return [], gr.update(choices=[], value=None), [], "⚠️ 请输入物品关键词"

    try:
        results = search_item(kw)
    except Exception as e:
        return [], gr.update(choices=[], value=None), [], f"❌ 查询失败：{e}"

    if not isinstance(results, list):
        return [], gr.update(choices=[], value=None), [], "❌ 返回格式不是 list"

    gallery = build_search_gallery(results)
    choices = build_dropdown_choices(results)
    default_val = choices[0] if choices else None
    return gallery, gr.update(choices=choices, value=default_val), results, f"✅ 搜索到 {len(results)} 个结果"


def parse_gallery_select(evt_value):
    if isinstance(evt_value, dict) and "caption" in evt_value:
        cap = evt_value["caption"]
    elif isinstance(evt_value, (tuple, list)) and len(evt_value) >= 2:
        cap = evt_value[1]
    else:
        cap = evt_value

    if isinstance(cap, str):
        return cap.splitlines()[0].strip()  # name (objectID)
    return None


def add_item(selected_label, reserve_dict):
    reserve_dict = reserve_dict or {}
    if not selected_label:
        return reserve_dict, "⚠️ 请先选择一个道具"

    name = selected_label.split("(", 1)[0].strip()
    reserve_dict[name] = reserve_dict.get(name, 0) + 1
    return reserve_dict, f"✅ 已添加：{name}"


def remove_item(selected_label, reserve_dict):
    reserve_dict = reserve_dict or {}
    if not selected_label:
        return reserve_dict, "⚠️ 请先选择一个道具"

    name = selected_label.split("(", 1)[0].strip()
    if name not in reserve_dict:
        return reserve_dict, "⚠️ 该道具不在预留列表中"

    reserve_dict[name] -= 1
    if reserve_dict[name] <= 0:
        del reserve_dict[name]
    return reserve_dict, f"🗑 已减少：{name}"


def confirm_reserve(reserve_dict):
    return format_reserve_text(reserve_dict or {})


def build():
    with gr.Group(visible=False) as page:
        gr.HTML("<div class='panel'><div class='title'>预留物品选择</div></div>")

        search_box = gr.Textbox(label="搜索道具", placeholder="输入关键字，例如：海洋之泪")
        btn_search_confirm = gr.Button("确认搜索", variant="primary")
        search_hint = gr.Markdown("")

        gallery = gr.Gallery(
            value=[],
            label="搜索结果",
            columns=5,
            height=260,
            elem_id="search-gallery",
        )

        picker = gr.Dropdown(
            choices=[],
            label="当前选中道具（objectName + objectID）",
            value=None,
        )

        hint = gr.Markdown("")
        with gr.Row(elem_classes=["center-btn"]):
            btn_add = gr.Button("添加 +1", variant="primary")
            btn_remove = gr.Button("减少 -1")

        reserve_preview = gr.Textbox(
            value=format_reserve_text({"留声机": 1, "机甲": 2, "红卡": 5}),
            interactive=False,
            label="当前预留物品",
        )

        with gr.Row(elem_classes=["center-btn"]):
            btn_picker_cancel = gr.Button("取消")
            btn_picker_ok = gr.Button("确定", variant="primary")

    return page, {
        "search_box": search_box,
        "btn_search_confirm": btn_search_confirm,
        "search_hint": search_hint,
        "gallery": gallery,
        "picker": picker,
        "hint": hint,
        "btn_add": btn_add,
        "btn_remove": btn_remove,
        "reserve_preview": reserve_preview,
        "btn_picker_cancel": btn_picker_cancel,
        "btn_picker_ok": btn_picker_ok,
    }
