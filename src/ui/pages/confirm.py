# src/ui/pages/confirm.py
import gradio as gr


def build():
    with gr.Group(visible=False) as page:
        confirm_text = gr.Textbox(
            value="(这里会生成最终提交日志内容)",
            interactive=False,
            show_label=False,
            lines=12,
            elem_classes=["panel"],
        )

        remark = gr.Textbox(
            label="备注（可选）",
            placeholder="例如：今天上号有延迟/价格已手动微调/特殊情况说明…",
            lines=2,
        )

        with gr.Row(elem_classes=["center-btn"]):
            btn_cancel = gr.Button("【取消】")
            # 默认禁用，进入页面时由 page.py 根据截图情况开启
            btn_confirm = gr.Button("【确认】", variant="primary", interactive=False)

    return page, {
        "confirm_text": confirm_text,
        "remark": remark,
        "btn_cancel": btn_cancel,
        "btn_confirm": btn_confirm,
    }
