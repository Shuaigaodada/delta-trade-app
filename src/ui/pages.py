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
from src.services.request_service import search_item, get_latest_price  # ✅ 用到两个接口


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


def build_app(css: str):
    # ======================
    # 页面跳转
    # ======================
    def goto_settlement():
        return show_pages(False, True, False, False, False, False, False)

    def back_to_home():
        return show_pages(True, False, False, False, False, False, False)

    def back_to_settlement():
        return show_pages(False, True, False, False, False, False, False)

    def goto_item_picker():
        return show_pages(False, False, False, True, False, False, False)

    def back_from_picker():
        return show_pages(False, True, False, False, False, False, False)

    def back_from_log_detail():
        return show_pages(True, False, False, False, False, False, False)

    def goto_reserve_manager():
        return show_pages(False, False, False, False, False, False, True)

    def back_from_reserve_manager():
        return show_pages(False, True, False, False, False, False, False)

    # ======================
    # 结算页重置
    # ======================
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

    # ======================
    # OCR 实时预览
    # ======================
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

    # ======================
    # 提交（不改你原逻辑）
    # ======================
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

        p1, p2, p3, p4, p5, p6, p7 = show_pages(False, False, True, False, False, False, False)
        return gr.update(value=msg), p1, p2, p3, p4, p5, p6, p7

    # ======================
    # Page4：搜索展示
    # ======================
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

    # ======================
    # 预留物品：加减（保持用 name 做 key）
    # ======================
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

    # ======================
    # 预留物品总均价计算（核心）
    # ======================
    def _pick_best_match(results: list[dict], target_name: str):
        """
        优先 exact match（objectName == target_name），否则取第一个
        """
        if not results:
            return None
        for x in results:
            if (x.get("objectName") or "").strip() == target_name.strip():
                return x
        return results[0]

    def calc_reserve_total_value(reserve_dict: dict):
        """
        返回：显示文本（包含总价 + 明细），以及一个简短状态提示
        说明：
        - latest_price_map 的 avgPrice 可能是“原始单位”（不是 k）
        - 我同时给一个 /1000 的 k 换算展示，方便你对齐 UI 的 k
        """
        reserve_dict = reserve_dict or {}
        if not reserve_dict:
            return "预留物品最新均价合计：0\n\n(无预留物品)", "（无预留物品）"

        # 1) 先把每个 name -> objectID 找出来
        name_to_oid = {}
        missing = []
        for name in reserve_dict.keys():
            try:
                results = search_item(name)
            except Exception:
                results = []
            best = _pick_best_match(results, name)
            if not best or not best.get("objectID"):
                missing.append(name)
                continue
            name_to_oid[name] = int(best["objectID"])

        if not name_to_oid:
            return "预留物品最新均价合计：0\n\n（全部物品都没匹配到 objectID）", "❌ 没匹配到任何 objectID"

        # 2) 批量取最新均价
        oids = list(name_to_oid.values())
        latest_map = get_latest_price(oids) or {}

        # 3) 汇总
        total_raw = 0
        lines = []
        for name, cnt in reserve_dict.items():
            oid = name_to_oid.get(name)
            if oid is None:
                lines.append(f"- {name} x{cnt}：未找到 objectID")
                continue

            info = latest_map.get(str(oid)) or {}
            avg = info.get("avgPrice", None)
            if avg is None:
                lines.append(f"- {name} x{cnt}（{oid}）：未返回最新均价")
                continue

            try:
                avg = int(avg)
            except Exception:
                lines.append(f"- {name} x{cnt}（{oid}）：均价解析失败")
                continue

            subtotal = avg * int(cnt)
            total_raw += subtotal
            lines.append(f"- {name} x{cnt}（{oid}）：{avg}  => 小计 {subtotal}")

        # 你 UI 全是 k：这里顺便给一个粗略换算（不保证单位完全一致，看你接口实际单位）
        total_k = round(total_raw / 1000)

        text = (
            f"预留物品最新均价合计：{total_raw}\n"
            f"约合：{total_k}k（仅按 /1000 换算展示）\n\n"
            + "\n".join(lines)
        )

        hint = "✅ 已刷新最新均价"
        if missing:
            hint += f"（{len(missing)} 个未匹配：{', '.join(missing[:3])}{'...' if len(missing)>3 else ''}）"

        return text, hint

    # ======================
    # Page7：预留物品管理
    # ======================
    def reserve_choices(reserve_dict: dict):
        reserve_dict = reserve_dict or {}
        return [f"{k} x{v}" for k, v in reserve_dict.items()]

    def delete_one_reserve(selected, reserve_dict):
        reserve_dict = reserve_dict or {}
        if not selected:
            return reserve_dict, "⚠️ 请选择一个要删除的预留物品"
        # selected: "海洋之泪 x1"
        name = selected.split(" x", 1)[0].strip()
        if name in reserve_dict:
            del reserve_dict[name]
            return reserve_dict, f"🗑 已删除：{name}"
        return reserve_dict, "⚠️ 该物品不在预留列表中"

    def clear_reserve(reserve_dict):
        return {}, "🧹 已清空全部预留物品"

    # ======================
    # 日志：刷新/详情/分页（你原来的）
    # ======================
    def refresh_logs():
        rows, metas = make_log_table_meta(20)
        return rows, metas

    def open_log_detail(evt: gr.SelectData, metas):
        p1, p2, p3, p4, p5, p6, p7 = show_pages(False, False, False, False, True, False, False)

        if (evt is None) or (evt.index is None):
            return gr.update(value="(未选中日志)"), p1, p2, p3, p4, p5, p6, p7

        r, c = evt.index
        if not metas or r < 0 or r >= len(metas):
            return gr.update(value="(解析选中行失败)"), p1, p2, p3, p4, p5, p6, p7

        fn = metas[r]["file"]
        content = read_log_file_by_filename(fn)
        title = filename_to_display_time(fn)
        full = f"日志时间：{title}\n\n{content}"
        return gr.update(value=full), p1, p2, p3, p4, p5, p6, p7

    def open_more_page():
        rows, metas, info, page = make_log_table_page_meta(1, PAGE_SIZE)
        p1, p2, p3, p4, p5, p6, p7 = show_pages(False, False, False, False, False, True, False)
        return gr.update(value=rows), gr.update(value=info), page, metas, p1, p2, p3, p4, p5, p6, p7

    def more_prev(page):
        rows, metas, info, page = make_log_table_page_meta(page - 1, PAGE_SIZE)
        return gr.update(value=rows), gr.update(value=info), page, metas

    def more_next(page):
        rows, metas, info, page = make_log_table_page_meta(page + 1, PAGE_SIZE)
        return gr.update(value=rows), gr.update(value=info), page, metas

    # ======================
    # UI
    # ======================
    with gr.Blocks() as demo:
        gr.HTML("<div id='main-container'>")

        reserve_state = gr.State({"留声机": 1, "机甲": 2, "红卡": 5})

        # OCR states
        up_coin_state = gr.State(None)
        down_coin_state = gr.State(None)

        # 日志 meta states
        init_rows, init_meta = make_log_table_meta(20)
        log_meta_state = gr.State(init_meta)

        # 搜索结果 state
        search_results_state = gr.State([])

        # ================= Page1 =================
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

        # ================= Page2 =================
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

            # ✅ 新增：预留物品最新均价合计显示
            reserve_total_text = gr.Textbox(
                value="预留物品最新均价合计：点击“刷新均价”计算",
                interactive=False,
                show_label=False,
                lines=8,
                elem_classes=["panel"],
            )
            reserve_total_hint = gr.Markdown("")

            with gr.Row(elem_classes=["center-btn"]):
                btn_add_reserve = gr.Button("【预留物品添加】")
                btn_manage_reserve = gr.Button("【管理/删除预留物品】")
                btn_refresh_price = gr.Button("刷新均价", variant="primary")

            with gr.Row(elem_classes=["center-btn"]):
                btn_submit = gr.Button("【提交】", variant="primary")
                btn_back_home = gr.Button("返回主页")

        # ================= Page3 =================
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

        # ================= Page4 =================
        with gr.Group(visible=False) as page4:
            gr.HTML("<div class='panel'><div class='title'>预留物品选择</div></div>")

            search_box = gr.Textbox(label="搜索道具", placeholder="输入关键字，例如：海洋之泪")
            btn_search_confirm = gr.Button("确认搜索", variant="primary")
            search_hint = gr.Markdown("")

            gallery = gr.Gallery(
                value=[],
                label="搜索结果",
                columns=5,
                height=260,
                elem_id="search-gallery"   # ✅ 给 CSS 精准命中
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

        # ================= Page5 =================
        with gr.Group(visible=False) as page5:
            gr.HTML("<div class='panel'><div class='title'>日志详情</div></div>")
            log_detail_text = gr.Textbox(value="", interactive=False, show_label=False, lines=16, elem_classes=["panel"])
            with gr.Row(elem_classes=["center-btn"]):
                btn_log_ok = gr.Button("确认", variant="primary")

        # ================= Page6 =================
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

        # ================= Page7（新增） =================
        with gr.Group(visible=False) as page7:
            gr.HTML("<div class='panel'><div class='title'>预留物品管理（快速删除）</div></div>")

            reserve_manage_dd = gr.Dropdown(
                choices=[],
                label="当前预留物品（选择后可删除）",
                value=None,
            )

            manage_hint = gr.Markdown("")
            with gr.Row(elem_classes=["center-btn"]):
                btn_delete_one = gr.Button("删除选中物品", variant="primary")
                btn_clear_all = gr.Button("清空全部")

            # 同样展示最新均价合计
            reserve_total_text2 = gr.Textbox(
                value="预留物品最新均价合计：点击“刷新均价”计算",
                interactive=False,
                show_label=False,
                lines=8,
                elem_classes=["panel"],
            )
            reserve_total_hint2 = gr.Markdown("")
            with gr.Row(elem_classes=["center-btn"]):
                btn_refresh_price2 = gr.Button("刷新均价", variant="primary")
                btn_mgr_back = gr.Button("返回结算页")

        gr.HTML("</div>")

        # =======================
        # 绑定：页面跳转
        # =======================
        btn_settlement.click(
            fn=goto_settlement,
            outputs=[page1, page2, page3, page4, page5, page6, page7],
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

        btn_back_home.click(fn=back_to_home, outputs=[page1, page2, page3, page4, page5, page6, page7])

        btn_add_reserve.click(fn=goto_item_picker, outputs=[page1, page2, page3, page4, page5, page6, page7])
        btn_picker_cancel.click(fn=back_from_picker, outputs=[page1, page2, page3, page4, page5, page6, page7])

        btn_cancel.click(fn=back_to_settlement, outputs=[page1, page2, page3, page4, page5, page6, page7])
        btn_confirm.click(fn=back_to_home, outputs=[page1, page2, page3, page4, page5, page6, page7])

        # 管理页跳转
        btn_manage_reserve.click(
            fn=goto_reserve_manager,
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        ).then(
            fn=lambda d: gr.update(choices=reserve_choices(d), value=(reserve_choices(d)[0] if reserve_choices(d) else None)),
            inputs=reserve_state,
            outputs=reserve_manage_dd,
        )

        btn_mgr_back.click(fn=back_from_reserve_manager, outputs=[page1, page2, page3, page4, page5, page6, page7])

        # =======================
        # OCR 实时预览
        # =======================
        img_up.change(fn=ocr_preview, inputs=img_up, outputs=[up_coin_state, up_coin_preview, up_fail_hint, up_hint_img])
        img_down.change(fn=ocr_preview, inputs=img_down, outputs=[down_coin_state, down_coin_preview, down_fail_hint, down_hint_img])

        # =======================
        # 提交
        # =======================
        btn_submit.click(
            fn=submit_with_ocr,
            inputs=[up_coin_state, down_coin_state, reserve_state],
            outputs=[confirm_text, page1, page2, page3, page4, page5, page6, page7],
        )

        # =======================
        # Page4 搜索
        # =======================
        btn_search_confirm.click(
            fn=on_search_confirm,
            inputs=[search_box],
            outputs=[gallery, picker, search_results_state, search_hint],
        )
        gallery.select(fn=parse_gallery_select, outputs=picker)

        # =======================
        # 预留物品 加减 + 刷新预览
        # =======================
        btn_add.click(
            fn=add_item,
            inputs=[picker, reserve_state],
            outputs=[reserve_state, hint],
        ).then(
            fn=lambda d: format_reserve_text(d),
            inputs=reserve_state,
            outputs=reserve_preview,
        )

        btn_remove.click(
            fn=remove_item,
            inputs=[picker, reserve_state],
            outputs=[reserve_state, hint],
        ).then(
            fn=lambda d: format_reserve_text(d),
            inputs=reserve_state,
            outputs=reserve_preview,
        )

        # 点击“确定”回结算页，同时刷新结算页显示的预留文本
        btn_picker_ok.click(
            fn=confirm_reserve,
            inputs=reserve_state,
            outputs=reserve_display,
        ).then(
            fn=back_from_picker,
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        )

        # =======================
        # 刷新均价（Page2 / Page7）
        # =======================
        btn_refresh_price.click(
            fn=calc_reserve_total_value,
            inputs=reserve_state,
            outputs=[reserve_total_text, reserve_total_hint],
        )

        btn_refresh_price2.click(
            fn=calc_reserve_total_value,
            inputs=reserve_state,
            outputs=[reserve_total_text2, reserve_total_hint2],
        )

        # =======================
        # Page7 删除/清空
        # =======================
        btn_delete_one.click(
            fn=delete_one_reserve,
            inputs=[reserve_manage_dd, reserve_state],
            outputs=[reserve_state, manage_hint],
        ).then(
            fn=lambda d: gr.update(choices=reserve_choices(d), value=(reserve_choices(d)[0] if reserve_choices(d) else None)),
            inputs=reserve_state,
            outputs=reserve_manage_dd,
        ).then(
            fn=lambda d: format_reserve_text(d),
            inputs=reserve_state,
            outputs=reserve_display,
        )

        btn_clear_all.click(
            fn=clear_reserve,
            inputs=reserve_state,
            outputs=[reserve_state, manage_hint],
        ).then(
            fn=lambda d: gr.update(choices=reserve_choices(d), value=None),
            inputs=reserve_state,
            outputs=reserve_manage_dd,
        ).then(
            fn=lambda d: format_reserve_text(d),
            inputs=reserve_state,
            outputs=reserve_display,
        )

        # =======================
        # 日志刷新/详情/分页
        # =======================
        btn_refresh_logs.click(fn=refresh_logs, outputs=[log_table, log_meta_state])

        log_table.select(
            fn=open_log_detail,
            inputs=[log_meta_state],
            outputs=[log_detail_text, page1, page2, page3, page4, page5, page6, page7],
        )
        btn_log_ok.click(fn=back_from_log_detail, outputs=[page1, page2, page3, page4, page5, page6, page7])

        btn_more.click(
            fn=open_more_page,
            outputs=[more_table, more_info, more_page_state, more_meta_state, page1, page2, page3, page4, page5, page6, page7],
        )
        btn_prev.click(fn=more_prev, inputs=more_page_state, outputs=[more_table, more_info, more_page_state, more_meta_state])
        btn_next.click(fn=more_next, inputs=more_page_state, outputs=[more_table, more_info, more_page_state, more_meta_state])

        more_table.select(
            fn=open_log_detail,
            inputs=[more_meta_state],
            outputs=[log_detail_text, page1, page2, page3, page4, page5, page6, page7],
        )
        btn_more_back.click(fn=back_to_home, outputs=[page1, page2, page3, page4, page5, page6, page7])

    return demo
