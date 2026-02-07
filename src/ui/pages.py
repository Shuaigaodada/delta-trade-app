import os
import gradio as gr

from src.config import PAGE_SIZE, OCR_HINT_IMAGE
from src.services.logs_service import (
    make_log_table_meta,
    make_log_table_page_meta,
    read_log_file_by_filename,
    filename_to_display_time,
)
from src.services.ocr_service import extract_pure_coin_k
from src.services.request_service import search_item  # ✅ 你要调用的接口


def format_reserve_text(reserve_dict: dict):
    if not reserve_dict:
        return "无"
    return ", ".join([f"{k}x{v}" for k, v in reserve_dict.items()])


def home_stats_text():
    return (
        "比例 1:22.22w\n"
        "当前预付款: 450元\n"
        "当前账号纯币: 12031k\n"
        "知更大人今日已跑: 30231k (挖槽 牛蛙!)"
    )


def show_pages(p1, p2, p3, p4, p5, p6):
    return (
        gr.update(visible=p1),
        gr.update(visible=p2),
        gr.update(visible=p3),
        gr.update(visible=p4),
        gr.update(visible=p5),
        gr.update(visible=p6),
    )


def build_app(css: str):
    # ===== 页面跳转 =====
    def goto_settlement():
        return show_pages(False, True, False, False, False, False)

    def back_to_home():
        return show_pages(True, False, False, False, False, False)

    def goto_confirm():
        return show_pages(False, False, True, False, False, False)

    def back_to_settlement():
        return show_pages(False, True, False, False, False, False)

    def goto_item_picker():
        return show_pages(False, False, False, True, False, False)

    def back_from_picker():
        return show_pages(False, True, False, False, False, False)

    def back_from_log_detail():
        return show_pages(True, False, False, False, False, False)

    # ===== 结算页重置 =====
    def reset_settlement_ui():
        hint_img_exists = os.path.exists(OCR_HINT_IMAGE)
        return (
            gr.update(value=None),   # img_up
            gr.update(value=None),   # img_down
            None,                    # up_coin_state
            None,                    # down_coin_state
            gr.update(value="未识别"),  # up_coin_preview
            gr.update(value="未识别"),  # down_coin_preview
            gr.update(value=""),        # up_fail_hint
            gr.update(value=""),        # down_fail_hint
            gr.update(visible=False, value=OCR_HINT_IMAGE if hint_img_exists else None),  # up_hint_img
            gr.update(visible=False, value=OCR_HINT_IMAGE if hint_img_exists else None),  # down_hint_img
        )

    # ===== OCR 实时预览 =====
    def ocr_preview(image_path: str):
        hint_img_exists = os.path.exists(OCR_HINT_IMAGE)

        if not image_path:
            return None, "未识别", "", gr.update(visible=False, value=OCR_HINT_IMAGE if hint_img_exists else None)

        v = extract_pure_coin_k(image_path, debug=True)

        if v is None:
            fail_md = (
                "⚠️ **未识别到纯币**（右上角 `xxxxxk`）  \n"
                "建议：**裁剪/放大右上角纯币区域**，确保数字清晰不糊、不要被图标遮挡。  \n"
            )
            img_upd = gr.update(visible=True, value=OCR_HINT_IMAGE) if hint_img_exists else gr.update(visible=False)
            return None, "⚠️ 未识别到纯币", fail_md, img_upd

        return int(v), f"✅ 识别成功：{int(v)}k", "", gr.update(visible=False, value=OCR_HINT_IMAGE if hint_img_exists else None)

    # ===== 提交：使用实时识别结果（不重复OCR）=====
    def submit_with_ocr(up_k, down_k, reserve_dict):
        reserve_text = format_reserve_text(reserve_dict or {})

        if up_k is None or down_k is None:
            msg = "⚠️ 识别失败：请先上传两张截图并确保都识别成功。\n\n"
            msg += f"上号识别：{up_k}\n下号识别：{down_k}\n"
            msg += f"预留物品：{reserve_text}\n"
        else:
            diff_k = int(down_k) - int(up_k)
            msg = (
                "注意，以下是最终提交的日志，请阅读后确保没有任何问题。\n"
                f"上号纯币：{int(up_k)}k\n"
                f"下号纯币：{int(down_k)}k\n"
                f"本次变化：{diff_k}k\n"
                f"预留物品：{reserve_text}\n"
            )

        p1, p2, p3, p4, p5, p6 = show_pages(False, False, True, False, False, False)
        return gr.update(value=msg), p1, p2, p3, p4, p5, p6

    # ===== 预留物品：加减 =====
    def add_item(selected_label, reserve_dict, search_results):
        reserve_dict = reserve_dict or {}
        if not selected_label:
            return reserve_dict, "⚠️ 请先选择一个道具"

        # selected_label 形如： "海洋之泪 (15080050142)"
        name = selected_label.split("(", 1)[0].strip()

        reserve_dict[name] = reserve_dict.get(name, 0) + 1
        return reserve_dict, f"✅ 已添加：{name}"

    def remove_item(selected_label, reserve_dict, search_results):
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

    # ===== 日志：刷新/详情/分页（使用 meta state 保存 filename）=====
    def refresh_logs():
        rows, metas = make_log_table_meta(20)
        return rows, metas

    def open_log_detail(evt: gr.SelectData, metas):
        p1, p2, p3, p4, p5, p6 = show_pages(False, False, False, False, True, False)

        if (evt is None) or (evt.index is None):
            return gr.update(value="(未选中日志)"), p1, p2, p3, p4, p5, p6

        r, c = evt.index
        if not metas or r < 0 or r >= len(metas):
            return gr.update(value="(解析选中行失败)"), p1, p2, p3, p4, p5, p6

        fn = metas[r]["file"]
        content = read_log_file_by_filename(fn)
        title = filename_to_display_time(fn)
        full = f"日志时间：{title}\n\n{content}"
        return gr.update(value=full), p1, p2, p3, p4, p5, p6

    def open_more_page():
        rows, metas, info, page = make_log_table_page_meta(1, PAGE_SIZE)
        p1, p2, p3, p4, p5, p6 = show_pages(False, False, False, False, False, True)
        return gr.update(value=rows), gr.update(value=info), page, metas, p1, p2, p3, p4, p5, p6

    def more_prev(page):
        rows, metas, info, page = make_log_table_page_meta(page - 1, PAGE_SIZE)
        return gr.update(value=rows), gr.update(value=info), page, metas

    def more_next(page):
        rows, metas, info, page = make_log_table_page_meta(page + 1, PAGE_SIZE)
        return gr.update(value=rows), gr.update(value=info), page, metas

    # ====== Page4: 搜索物品（核心改动）======
    def build_search_gallery(results: list[dict]):
        """
        Gallery item: (image_url, caption)
        caption 里包含：objectName (objectID) + avgPrice
        """
        gallery = []
        if not results:
            return gallery

        for x in results:
            name = x.get("objectName", "")
            oid = x.get("objectID", "")
            pic = x.get("pic", None)
            price = x.get("avgPrice", None)

            # 你要求：显示 objectId, objectName；图片右下角显示 avgPrice
            # 右下角“叠加显示”需要 CSS 才能做到，这里先把价格写在 caption 第二行
            caption = f"{name} ({oid})\n{price}"
            gallery.append((pic, caption))
        return gallery

    def build_dropdown_choices(results: list[dict]):
        # Dropdown 显示：objectName (objectID)
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
            return (
                [],                 # gallery
                gr.update(choices=[], value=None),  # dropdown
                [],                 # results_state
                "⚠️ 请输入物品关键词",  # hint
            )

        try:
            results = search_item(kw)  # ✅ 你要的调用
        except Exception as e:
            return (
                [],
                gr.update(choices=[], value=None),
                [],
                f"❌ 查询失败：{e}",
            )

        if not isinstance(results, list):
            return (
                [],
                gr.update(choices=[], value=None),
                [],
                "❌ 返回格式不是 list",
            )

        gallery = build_search_gallery(results)
        choices = build_dropdown_choices(results)
        default_val = choices[0] if choices else None
        hint = f"✅ 搜索到 {len(results)} 个结果"
        return gallery, gr.update(choices=choices, value=default_val), results, hint

    def parse_gallery_select(evt_value):
        """
        Gallery.select 的 evt_value 可能是：
        - dict: {"caption": "..."}
        - tuple/list: (img, caption)
        - str caption
        """
        if isinstance(evt_value, dict) and "caption" in evt_value:
            cap = evt_value["caption"]
        elif isinstance(evt_value, (tuple, list)) and len(evt_value) >= 2:
            cap = evt_value[1]
        else:
            cap = evt_value

        if isinstance(cap, str):
            # 第一行是：name (objectID)
            return cap.splitlines()[0].strip()
        return None

    # ===== UI =====
    with gr.Blocks() as demo:
        gr.HTML("<div id='main-container'>")

        reserve_state = gr.State({"留声机": 1, "机甲": 2, "红卡": 5})

        # OCR states
        up_coin_state = gr.State(None)
        down_coin_state = gr.State(None)

        # 日志 meta states
        init_rows, init_meta = make_log_table_meta(20)
        log_meta_state = gr.State(init_meta)

        # 搜索结果 state（保存 API 返回的 list[dict]）
        search_results_state = gr.State([])

        # ========== Page1 主页面 ==========
        with gr.Group(visible=True) as page1:
            stats = gr.Textbox(
                value=home_stats_text(),
                interactive=False,
                show_label=False,
                lines=5,
                elem_classes=["panel", "stats-center"],
            )

            btn_settlement = gr.Button("【结算】", variant="primary")

            log_table = gr.Dataframe(
                headers=["时间", "操作", "本次赚了"],
                value=init_rows,
                datatype=["str", "str", "str"],
                column_count=(3, "fixed"),
                interactive=False,
                wrap=True,
            )

            gr.Markdown("提示：点击某一行即可打开日志详情（手机上更好用）。")
            btn_refresh_logs = gr.Button("刷新日志")
            btn_more = gr.Button("【查询更多】")

        # ========== Page2 结算页面 ==========
        with gr.Group(visible=False) as page2:
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

            reserve_display = gr.Textbox(
                value=format_reserve_text({"留声机": 1, "机甲": 2, "红卡": 5}),
                interactive=False,
                show_label=False,
                elem_classes=["panel", "stats-center"],
            )

            with gr.Row(elem_classes=["center-btn"]):
                btn_add_reserve = gr.Button("【预留物品添加】")
                btn_submit = gr.Button("【提交】", variant="primary")

            with gr.Row(elem_classes=["center-btn"]):
                btn_back_home = gr.Button("返回主页")

        # ========== Page3 提交确认页面 ==========
        with gr.Group(visible=False) as page3:
            confirm_text = gr.Textbox(
                value="(这里会生成最终提交日志内容)",
                interactive=False,
                show_label=False,
                lines=12,
                elem_classes=["panel"],
            )
            with gr.Row(elem_classes=["center-btn"]):
                btn_cancel = gr.Button("【取消】")
                btn_confirm = gr.Button("【确认】", variant="primary")

        # ========== Page4 预留物品搜索页（大改） ==========
        with gr.Group(visible=False) as page4:
            gr.HTML("<div class='panel'><div class='title'>预留物品选择</div></div>")

            search_box = gr.Textbox(label="搜索道具", placeholder="输入关键字，例如：海洋之泪")
            btn_search_confirm = gr.Button("确认搜索", variant="primary")
            search_hint = gr.Markdown("")

            # 搜索结果展示
            gallery = gr.Gallery(
                value=[],
                label="搜索结果",
                columns=5,
                height=260,
                elem_id="search-gallery"
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

        # ========== Page5 日志详情页 ==========
        with gr.Group(visible=False) as page5:
            gr.HTML("<div class='panel'><div class='title'>日志详情</div></div>")
            log_detail_text = gr.Textbox(value="", interactive=False, show_label=False, lines=16, elem_classes=["panel"])
            with gr.Row(elem_classes=["center-btn"]):
                btn_log_ok = gr.Button("确认", variant="primary")

        # ========== Page6 日志查看更多页（分页） ==========
        with gr.Group(visible=False) as page6:
            gr.HTML("<div class='panel'><div class='title'>日志列表（查看更多）</div></div>")
            more_page_state = gr.State(1)
            more_meta_state = gr.State([])
            more_info = gr.Markdown("")

            more_table = gr.Dataframe(
                headers=["时间", "操作", "本次赚了"],
                value=init_rows,
                datatype=["str", "str", "str"],
                column_count=(3, "fixed"),
                interactive=False,
                wrap=True,
            )
            with gr.Row(elem_classes=["center-btn"]):
                btn_prev = gr.Button("上一页")
                btn_next = gr.Button("下一页")
            with gr.Row(elem_classes=["center-btn"]):
                btn_more_back = gr.Button("返回主页", variant="primary")

        gr.HTML("</div>")

        # =======================
        # 绑定：页面跳转
        # =======================
        btn_settlement.click(
            fn=goto_settlement,
            outputs=[page1, page2, page3, page4, page5, page6],
        ).then(
            fn=reset_settlement_ui,
            outputs=[
                img_up, img_down,
                up_coin_state, down_coin_state,
                up_coin_preview, down_coin_preview,
                up_fail_hint, down_fail_hint,
                up_hint_img, down_hint_img,
            ],
        )

        btn_back_home.click(fn=back_to_home, outputs=[page1, page2, page3, page4, page5, page6])

        btn_add_reserve.click(fn=goto_item_picker, outputs=[page1, page2, page3, page4, page5, page6])
        btn_picker_cancel.click(fn=back_from_picker, outputs=[page1, page2, page3, page4, page5, page6])

        btn_cancel.click(fn=back_to_settlement, outputs=[page1, page2, page3, page4, page5, page6])
        btn_confirm.click(fn=back_to_home, outputs=[page1, page2, page3, page4, page5, page6])

        # =======================
        # 绑定：OCR 实时预览
        # =======================
        img_up.change(
            fn=ocr_preview,
            inputs=img_up,
            outputs=[up_coin_state, up_coin_preview, up_fail_hint, up_hint_img],
        )

        img_down.change(
            fn=ocr_preview,
            inputs=img_down,
            outputs=[down_coin_state, down_coin_preview, down_fail_hint, down_hint_img],
        )

        # =======================
        # 绑定：提交
        # =======================
        btn_submit.click(
            fn=submit_with_ocr,
            inputs=[up_coin_state, down_coin_state, reserve_state],
            outputs=[confirm_text, page1, page2, page3, page4, page5, page6],
        )

        # =======================
        # 绑定：Page4 搜索确认（调用 request_service.search_item）
        # =======================
        btn_search_confirm.click(
            fn=on_search_confirm,
            inputs=[search_box],
            outputs=[gallery, picker, search_results_state, search_hint],
        )

        # 点击搜索结果，自动选中 dropdown
        gallery.select(fn=parse_gallery_select, outputs=picker)

        # =======================
        # 绑定：预留物品 加减
        # =======================
        btn_add.click(
            fn=add_item,
            inputs=[picker, reserve_state, search_results_state],
            outputs=[reserve_state, hint],
        ).then(
            fn=lambda d: format_reserve_text(d), inputs=reserve_state, outputs=reserve_preview
        )

        btn_remove.click(
            fn=remove_item,
            inputs=[picker, reserve_state, search_results_state],
            outputs=[reserve_state, hint],
        ).then(
            fn=lambda d: format_reserve_text(d), inputs=reserve_state, outputs=reserve_preview
        )

        btn_picker_ok.click(
            fn=confirm_reserve,
            inputs=reserve_state,
            outputs=reserve_display,
        ).then(
            fn=back_from_picker,
            outputs=[page1, page2, page3, page4, page5, page6],
        )

        # =======================
        # 绑定：日志列表刷新/详情
        # =======================
        btn_refresh_logs.click(fn=refresh_logs, outputs=[log_table, log_meta_state])

        log_table.select(
            fn=open_log_detail,
            inputs=[log_meta_state],
            outputs=[log_detail_text, page1, page2, page3, page4, page5, page6],
        )
        btn_log_ok.click(fn=back_from_log_detail, outputs=[page1, page2, page3, page4, page5, page6])

        # =======================
        # 绑定：查看更多分页
        # =======================
        btn_more.click(
            fn=open_more_page,
            outputs=[more_table, more_info, more_page_state, more_meta_state, page1, page2, page3, page4, page5, page6],
        )
        btn_prev.click(
            fn=more_prev,
            inputs=more_page_state,
            outputs=[more_table, more_info, more_page_state, more_meta_state],
        )
        btn_next.click(
            fn=more_next,
            inputs=more_page_state,
            outputs=[more_table, more_info, more_page_state, more_meta_state],
        )

        more_table.select(
            fn=open_log_detail,
            inputs=[more_meta_state],
            outputs=[log_detail_text, page1, page2, page3, page4, page5, page6],
        )
        btn_more_back.click(fn=back_to_home, outputs=[page1, page2, page3, page4, page5, page6])

    return demo
