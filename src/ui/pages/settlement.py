# src/ui/pages/settlement.py
import os
import gradio as gr

from src.config import OCR_HINT_IMAGE
from src.ui.pages.common import format_reserve_text


def reset_settlement_ui():
    hint_img_exists = os.path.exists(OCR_HINT_IMAGE)
    return (
        gr.update(value=None),  # img_up
        gr.update(value=None),  # img_down
        None,                   # up_coin_state
        None,                   # down_coin_state
        gr.update(value="未识别"),  # up_coin_preview
        gr.update(value="未识别"),  # down_coin_preview
        gr.update(value=""),        # up_fail_hint
        gr.update(value=""),        # down_fail_hint
        gr.update(visible=False, value=OCR_HINT_IMAGE if hint_img_exists else None),  # up_hint_img
        gr.update(visible=False, value=OCR_HINT_IMAGE if hint_img_exists else None),  # down_hint_img
    )


def build():
    with gr.Group(visible=False) as page:
        gr.HTML("<div class='panel'><div class='title'>结算页面</div></div>")

        img_up = gr.Image(label="上号时资产截图（请确保完整显示纯币）", type="filepath")
        up_coin_preview = gr.Textbox(label="上号纯币识别结果", value="未识别", interactive=False)
        up_fail_hint = gr.Markdown("")
        up_hint_img = gr.Image(
            label="示例（纯币位置）",
            value=OCR_HINT_IMAGE if os.path.exists(OCR_HINT_IMAGE) else None,
            interactive=False,
            visible=False,
        )

        img_down = gr.Image(label="下号时资产截图（请确保完整显示纯币）", type="filepath")
        down_coin_preview = gr.Textbox(label="下号纯币识别结果", value="未识别", interactive=False)
        down_fail_hint = gr.Markdown("")
        down_hint_img = gr.Image(
            label="示例（纯币位置）",
            value=OCR_HINT_IMAGE if os.path.exists(OCR_HINT_IMAGE) else None,
            interactive=False,
            visible=False,
        )


        # ✅ 文案更新：不再提示“刷新均价”（因为按钮移走了）
        reserve_total_text = gr.Textbox(
            value="无",
            interactive=False,
            show_label=False,
            lines=8,
            elem_classes=["panel"],
        )
        reserve_total_hint = gr.Markdown("")

        # ✅ 只保留一个按钮：管理预留物品
        with gr.Row(elem_classes=["center-btn"]):
            btn_manage_reserve = gr.Button("管理预留物品")

        # ✅ 返回主页左，提交右
        with gr.Row(elem_classes=["center-btn"]):
            btn_back_home = gr.Button("返回主页")
            btn_submit = gr.Button("【提交】", variant="primary")

    widgets = {
        "img_up": img_up,
        "up_coin_preview": up_coin_preview,
        "up_fail_hint": up_fail_hint,
        "up_hint_img": up_hint_img,

        "img_down": img_down,
        "down_coin_preview": down_coin_preview, 
        "down_fail_hint": down_fail_hint,
        "down_hint_img": down_hint_img,


        "reserve_total_text": reserve_total_text,
        "reserve_total_hint": reserve_total_hint,

        # ✅ 只保留这个入口
        "btn_manage_reserve": btn_manage_reserve,

        "btn_submit": btn_submit,
        "btn_back_home": btn_back_home,
    }

    return page, widgets
