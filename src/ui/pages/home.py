import gradio as gr
from src.ui.pages.common import home_stats_text


def build(init_rows):
    with gr.Group(visible=True) as page:
        stats = gr.Textbox(
            value=home_stats_text(),
            interactive=False,
            show_label=False,
            lines=5,
            elem_classes=["panel", "stats-center"],
        )

        btn_settlement = gr.Button("【结算】", variant="primary")

        log_table = gr.Dataframe(
            headers=["时间", "本次赚了"],
            value=init_rows,
            datatype=["str", "str"],
            column_count=(2, "fixed"),
            interactive=False,
            wrap=True,
        )

        gr.Markdown("提示：点击某一行即可打开日志详情（手机上更好用）。")
        btn_refresh_logs = gr.Button("刷新")
        btn_more = gr.Button("【查询更多】")

        # 右下角管理员入口（保持你 page.py 里用到的 key）
        btn_admin = gr.Button("管理员", elem_id="admin-fab")

        with gr.Group(visible=False, elem_id="admin-panel") as admin_panel:
            gr.HTML("<div class='panel'><div class='title'>管理员登录</div></div>")

            admin_user = gr.Textbox(label="账号", placeholder="请输入账号")
            admin_pass = gr.Textbox(label="密码", placeholder="请输入密码", type="password")
            admin_login_status = gr.Markdown("")

            with gr.Row(elem_classes=["center-btn"]):
                btn_admin_login = gr.Button("登录", variant="primary")
                btn_admin_close = gr.Button("关闭")

            with gr.Group(visible=False) as admin_edit_panel:
                gr.HTML("<div class='panel'><div class='title'>预付款管理</div></div>")

                admin_current = gr.Textbox(
                    label="当前预付款余额（元）",
                    interactive=False,
                )
                admin_new_total = gr.Number(
                    label="设置为（元，可为负数）",
                    value=0,
                )
                admin_save_status = gr.Markdown("")
                with gr.Row(elem_classes=["center-btn"]):
                    btn_admin_save = gr.Button("保存", variant="primary")

                # =========================
                # frameworkToken（管理员）
                # =========================
                gr.HTML("<div class='panel'><div class='title'>frameworkToken（管理员）</div></div>")

                admin_fw_token = gr.Textbox(
                    label="frameworkToken（纯文本一行）",
                    placeholder="粘贴 frameworkToken，保存后 request 会立刻读取最新值",
                    type="password",
                )
                admin_fw_status = gr.Markdown("")
                with gr.Row(elem_classes=["center-btn"]):
                    btn_admin_fw_save = gr.Button("保存 frameworkToken", variant="primary")
                    btn_admin_fw_reload = gr.Button("读取当前 frameworkToken")

                # ✅ 新增：扫码获取新 token
                gr.HTML("<div class='panel'><div class='title'>扫码获取新的 frameworkToken</div></div>")

                admin_qr_url = gr.Textbox(
                    label="二维码链接（用微信打开/扫码）",
                    interactive=False,
                    placeholder="点击“获取二维码”后生成",
                )
                admin_qr_tmp_token = gr.Textbox(
                    label="临时 frameworkToken（用于轮询 status）",
                    interactive=False,
                    placeholder="获取二维码后生成",
                )
                admin_qr_status = gr.Markdown("")

                with gr.Row(elem_classes=["center-btn"]):
                    btn_admin_qr_get = gr.Button("获取二维码", variant="primary")
                    btn_admin_qr_check = gr.Button("我已扫码，检查状态")
                    btn_admin_qr_apply = gr.Button("保存为当前 frameworkToken", variant="primary")

    return page, {
        "btn_settlement": btn_settlement,
        "log_table": log_table,
        "btn_refresh_logs": btn_refresh_logs,
        "btn_more": btn_more,
        "stats": stats,

        "btn_admin": btn_admin,
        "admin_panel": admin_panel,
        "admin_user": admin_user,
        "admin_pass": admin_pass,
        "admin_login_status": admin_login_status,
        "btn_admin_login": btn_admin_login,
        "btn_admin_close": btn_admin_close,

        "admin_edit_panel": admin_edit_panel,

        "admin_current": admin_current,
        "admin_new_total": admin_new_total,
        "admin_save_status": admin_save_status,
        "btn_admin_save": btn_admin_save,

        "admin_fw_token": admin_fw_token,
        "admin_fw_status": admin_fw_status,
        "btn_admin_fw_save": btn_admin_fw_save,
        "btn_admin_fw_reload": btn_admin_fw_reload,

        # ✅ 新增 keys
        "admin_qr_url": admin_qr_url,
        "admin_qr_tmp_token": admin_qr_tmp_token,
        "admin_qr_status": admin_qr_status,
        "btn_admin_qr_get": btn_admin_qr_get,
        "btn_admin_qr_check": btn_admin_qr_check,
        "btn_admin_qr_apply": btn_admin_qr_apply,
    }
