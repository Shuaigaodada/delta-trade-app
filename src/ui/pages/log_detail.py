# =========================
# src/ui/pages/log_detail.py
# =========================
import gradio as gr
from src.services import logs_service


def open_log_detail(evt: gr.SelectData, metas):
    if (evt is None) or (evt.index is None):
        return (
            gr.update(value="(未选中日志)"),
            gr.update(value=None),
            gr.update(value=None),
        )

    r, _c = evt.index
    if not metas or r < 0 or r >= len(metas):
        return (
            gr.update(value="(解析选中行失败)"),
            gr.update(value=None),
            gr.update(value=None),
        )

    dir_name = metas[r].get("dir")
    if not dir_name:
        return (
            gr.update(value="(日志目录为空)"),
            gr.update(value=None),
            gr.update(value=None),
        )

    content = logs_service.read_log_text_from_dir(dir_name)
    title = logs_service.dir_to_display_time(dir_name)
    up_img, down_img = logs_service.get_log_images(dir_name)

    full = f"日志时间：{title}\n\n{content}"
    return (
        gr.update(value=full),
        gr.update(value=up_img),
        gr.update(value=down_img),
    )


def build():
    with gr.Group(visible=False) as page:
        gr.HTML("<div class='panel'><div class='title'>日志详情</div></div>")

        with gr.Row():
            img_up = gr.Image(label="上号截图", type="filepath", interactive=False)
            img_down = gr.Image(label="下号截图", type="filepath", interactive=False)

        log_detail_text = gr.Textbox(
            value="",
            interactive=False,
            show_label=False,
            lines=16,
            elem_classes=["panel"],
        )

        with gr.Row(elem_classes=["center-btn"]):
            btn_log_ok = gr.Button("确认", variant="primary")

    return page, {
        "log_detail_text": log_detail_text,
        "img_up": img_up,
        "img_down": img_down,
        "btn_log_ok": btn_log_ok,
    }
