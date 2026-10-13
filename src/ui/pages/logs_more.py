# src/ui/pages/logs_more.py
import gradio as gr
from src.services.logs_service import make_log_table_page_meta


def open_more_page():
    rows, metas, info, page = make_log_table_page_meta(page=1)
    return (
        gr.update(value=rows),
        gr.update(value=info),
        1,
        metas,
    )


def more_prev(page: int):
    page = int(page or 1) - 1
    rows, metas, info, page = make_log_table_page_meta(page=page)
    return (
        gr.update(value=rows),
        gr.update(value=info),
        page,
        metas,
    )


def more_next(page: int):
    page = int(page or 1) + 1
    rows, metas, info, page = make_log_table_page_meta(page=page)
    return (
        gr.update(value=rows),
        gr.update(value=info),
        page,
        metas,
    )


def build(init_rows):
    with gr.Group(visible=False) as page:
        gr.HTML("<div class='panel'><div class='title'>更多日志</div></div>")

        more_info = gr.Markdown("")

        more_table = gr.Dataframe(
            headers=["时间", "本次赚了"],
            value=init_rows,
            interactive=False,
            col_count=(2, "fixed"),
            wrap=True,
        )

        more_page_state = gr.State(1)
        more_meta_state = gr.State([])

        with gr.Row(elem_classes=["center-btn"]):
            btn_prev = gr.Button("上一页")
            btn_next = gr.Button("下一页")

        with gr.Row(elem_classes=["center-btn"]):
            btn_more_back = gr.Button("返回主页")

    return page, {
        "more_table": more_table,
        "more_info": more_info,
        "more_page_state": more_page_state,
        "more_meta_state": more_meta_state,
        "btn_prev": btn_prev,
        "btn_next": btn_next,
        "btn_more_back": btn_more_back,
    }
