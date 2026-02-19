import gradio as gr
import os
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from pathlib import Path
import time
import random

from .pages import picker
from src.config import PAGE_SIZE, OCR_HINT_IMAGE
from src.services.logs_service import make_log_table_meta, make_log_table_page_meta
from src.services.ocr_service import extract_pure_coin_raw
from src.ui.pages.common import show_pages, home_stats_text
from src.services import logs_service
from src.services import finance_service
from src.services import request_service

from src.utils.money_format import format_money
from src.ui.pages import settlement, confirm, log_detail, logs_more, reserve_manager
from src.ui.pages import home as home_mod


TZ = ZoneInfo("America/Chicago")
FRAMEWORK_TOKEN_PATH = Path("data") / "frameworkToken"

_ITEM_RE = re.compile(r"(?P<price>\d+)\((?P<name>[^)]+)\)\*(?P<qty>\d+)")
_TOTAL_RE = re.compile(r"=\s*(?P<total>\d+)\s*$")

_EGG_DIR = Path("static/egg_audio")


def _pick_random_egg_audio_path() -> str | None:
    if not _EGG_DIR.exists():
        return None

    files: list[Path] = []
    for ext in ("*.m4a", "*.mp3", "*.wav"):
        files += list(_EGG_DIR.glob(ext))

    if not files:
        return None

    return random.choice(files).as_posix()


def _audio_to_data_uri(path: str) -> str | None:
    """
    把音频读成 data: URI（不依赖 /file 静态路由）
    支持：m4a/mp3/wav
    """
    try:
        p = Path(path)
        if not p.exists():
            return None

        b = p.read_bytes()
        enc = base64.b64encode(b).decode("ascii")

        suf = p.suffix.lower()
        mime = "audio/mp4"   # m4a
        if suf == ".mp3":
            mime = "audio/mpeg"
        elif suf == ".wav":
            mime = "audio/wav"

        return f"data:{mime};base64,{enc}"
    except Exception:
        return None


def format_reserve_expr_for_settlement(expr_raw: str) -> str:
    if not expr_raw:
        return "无"
    s = str(expr_raw).strip()
    if not s:
        return "无"

    # 只做“整段匹配”，不要用 `"无" in s`
    if s in ("无", "（无预留物品）", "(无预留物品)"):
        return "无"

    def _rep_item(m: re.Match) -> str:
        price = int(m.group("price"))
        name = m.group("name")
        qty = int(m.group("qty"))
        return f"{format_money(price)}({name})*{qty}"

    s = _ITEM_RE.sub(_rep_item, s)

    m_total = _TOTAL_RE.search(s)
    if m_total:
        total = int(m_total.group("total"))
        s = _TOTAL_RE.sub(f"= {format_money(total)}", s)

    return s


def _read_framework_token() -> str:
    try:
        return FRAMEWORK_TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _save_framework_token(token: str) -> str:
    t = (token or "").strip()
    FRAMEWORK_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRAMEWORK_TOKEN_PATH.write_text(t, encoding="utf-8")
    try:
        request_service.write_framework_token(t)
    except Exception:
        pass
    return t


def _fmt_seconds_left(sec: int) -> str:
    try:
        sec = int(sec)
    except Exception:
        return "未知"
    if sec < 0:
        return "已过期"
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h}h{m}m"
    if m > 0:
        return f"{m}m{s}s"
    return f"{s}s"


def build_app(css: str):
    def _tick(x):
        try:
            return int(x or 0) + 1
        except Exception:
            return 1

    def goto_settlement():
        return show_pages(False, True, False, False, False, False, False)

    def back_to_home():
        return show_pages(True, False, False, False, False, False, False)

    def back_to_settlement():
        return show_pages(False, True, False, False, False, False, False)

    def goto_confirm():
        return show_pages(False, False, True, False, False, False, False)

    def back_from_log_detail():
        return show_pages(True, False, False, False, False, False, False)

    def goto_reserve_manager():
        return show_pages(False, False, False, False, False, False, True)

    def back_from_reserve_manager():
        return show_pages(False, True, False, False, False, False, False)

    # ======================
    # OCR 预览
    # ======================
    def ocr_preview(image_path: str):
        hint_img_exists = os.path.exists(OCR_HINT_IMAGE)

        if not image_path:
            return None, "未识别", "", gr.update(visible=False, value=OCR_HINT_IMAGE if hint_img_exists else None)

        v_raw = extract_pure_coin_raw(image_path)
        if v_raw is None:
            fail_md = (
                "⚠️ **未识别到纯币**（右上角数字区域）  \n"
                "建议：**裁剪/放大右上角纯币区域**，确保数字清晰不糊、不要被图标遮挡。  \n"
            )
            img_upd = gr.update(visible=True, value=OCR_HINT_IMAGE) if hint_img_exists else gr.update(visible=False)
            return None, "⚠️ 未识别到纯币", fail_md, img_upd

        return int(v_raw), f"✅ 识别成功：{format_money(v_raw)}", "", gr.update(
            visible=False, value=OCR_HINT_IMAGE if hint_img_exists else None
        )

    # ======================
    # 提交确认文本
    # ======================
    def submit_with_ocr(img_up_path, img_down_path, up_raw, down_raw, reserve_expr_raw: str):
        has_both_imgs = bool(img_up_path) and bool(img_down_path)

        reserve_line, reserve_total_raw = reserve_manager.build_confirm_reserve_line(reserve_expr_raw)

        try:
            reserve_total_raw_int = int(reserve_total_raw or 0)
            reserve_line = f"预留物品总价值：{format_money(reserve_total_raw_int)}"
        except Exception:
            reserve_total_raw_int = 0

        prepay_yuan = float(finance_service.get_prepayment_total() or 0)

        if up_raw is None or down_raw is None:
            msg = (
                "注意，以下是最终提交的日志，请阅读后确保没有任何问题。\n"
                f"上号纯币：{format_money(up_raw)}\n"
                f"下号纯币：{format_money(down_raw)}\n"
                f"{reserve_line}\n"
                f"\n本次变化：?\n"
            )
        else:
            up_raw = int(up_raw)
            down_raw = int(down_raw)

            diff_raw = down_raw - up_raw
            diff_with_reserve_raw = diff_raw + int(reserve_total_raw_int)

            change_w = diff_with_reserve_raw / 10_000.0
            change_yuan = change_w / 22.22
            settlement_yuan = prepay_yuan - change_yuan

            msg = (
                "注意，以下是最终提交的日志，请阅读后确保没有任何问题。\n"
                f"上号纯币：{format_money(up_raw)}\n"
                f"下号纯币：{format_money(down_raw)}\n"
                f"{reserve_line}\n"
                f"\n本次变化：{format_money(diff_with_reserve_raw)}\n"
                f"本次折合：{change_yuan:.2f}元\n"
                f"预付款：{prepay_yuan:.2f}元\n"
                f"结算金额：{settlement_yuan:.2f}元\n"
            )

        p1, p2, p3, p4, p5, p6, p7 = goto_confirm()
        return (
            gr.update(value=msg),
            gr.update(interactive=has_both_imgs),
            gr.update(value=""),
            p1, p2, p3, p4, p5, p6, p7
        )

    # ======================
    # stats：跨天自动刷新
    # ======================
    def _today_key() -> str:
        return datetime.now(TZ).strftime("%Y-%m-%d")

    def tick_midnight_refresh(last_day: str):
        cur = _today_key()
        if last_day != cur:
            return cur, gr.update(value=home_stats_text())
        return last_day, gr.update()

    def refresh_logs_and_stats():
        rows, metas = make_log_table_meta(20)
        return rows, metas, gr.update(value=home_stats_text())

    # ======================
    # ✅ 提交后：刷新 + 仅本轮第一次塞一个音频（data uri）
    # ======================
    def refresh_after_confirm_and_pick_audio(egg_played: bool):
        rows, metas = make_log_table_meta(20)
        stats_upd = gr.update(value=home_stats_text())

        if egg_played:
            return rows, metas, stats_upd, gr.update(value=""), gr.update(), True

        audio_path = _pick_random_egg_audio_path()
        if not audio_path:
            return rows, metas, stats_upd, gr.update(value=""), gr.update(), False

        data_uri = _audio_to_data_uri(audio_path)
        if not data_uri:
            return rows, metas, stats_upd, gr.update(value=""), gr.update(), False

        return rows, metas, stats_upd, gr.update(value=data_uri), gr.update(), True

    # ======================
    # ✅ 管理员（保持你原逻辑）
    # ======================
    ADMIN_USER = "laogao0113"
    ADMIN_PASS = "gao83282112"

    def admin_open():
        return (
            gr.update(visible=True),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(visible=False),

            gr.update(value=""),
            gr.update(value=0),
            gr.update(value=""),

            gr.update(value=""),
            gr.update(value=""),

            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
        )

    def admin_close():
        return (
            gr.update(visible=False),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(visible=False),

            gr.update(value=""),
            gr.update(value=0),
            gr.update(value=""),

            gr.update(value=""),
            gr.update(value=""),

            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
        )

    def admin_login(user: str, pwd: str):
        user = (user or "").strip()
        pwd = (pwd or "").strip()

        if user != ADMIN_USER or pwd != ADMIN_PASS:
            return (
                gr.update(value="❌ 账号或密码错误"),
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(value=0),
                gr.update(value=""),

                gr.update(value=""),
                gr.update(value=""),

                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
            )

        cur = float(finance_service.get_prepayment_total() or 0)
        ft = _read_framework_token()
        return (
            gr.update(value="✅ 登录成功"),
            gr.update(visible=True),
            gr.update(value=f"{cur:.2f}"),
            gr.update(value=cur),
            gr.update(value=""),

            gr.update(value=ft),
            gr.update(value=""),

            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
        )

    def admin_save(new_total_yuan: float):
        r = finance_service.admin_set_prepayment_total(float(new_total_yuan or 0))
        cur = float(finance_service.get_prepayment_total() or 0)
        msg = f"✅ 已保存：{r['old']:.2f} → {r['new']:.2f}（变动 {r['delta']:+.2f}）"
        return (
            gr.update(value=f"{cur:.2f}"),
            gr.update(value=cur),
            gr.update(value=msg),
            gr.update(value=home_stats_text()),
        )

    def admin_fw_save(token: str):
        t = (token or "").strip()
        if not t:
            return gr.update(value=""), "⚠️ frameworkToken 不能为空"
        try:
            _save_framework_token(t)
            return gr.update(value=t), "✅ 已保存（后续请求会读取最新 frameworkToken）"
        except Exception as e:
            return gr.update(value=t), f"❌ 保存失败：{e}"

    def admin_fw_reload():
        t = _read_framework_token()
        if not t:
            return gr.update(value=""), "（当前 data/frameworkToken 为空或不存在）"
        return gr.update(value=t), "✅ 已读取当前 frameworkToken"

    def admin_qr_get():
        j = request_service.api_wechat_qr()
        if not isinstance(j, dict):
            return "", "", "❌ 获取二维码失败：返回非 dict"
        code = j.get("code")
        success = j.get("success")
        if (success is False) or (code is not None and code not in (0, "0")):
            return "", "", f"❌ 获取二维码失败：{j.get('message') or j.get('msg') or j}"

        fw = j.get("frameworkToken") or j.get("framework_token") or j.get("token")
        qr = j.get("qr_image") or j.get("qrImage") or j.get("qr") or j.get("qrUrl")
        exp = j.get("expire") or j.get("expiresAt") or j.get("expireAt")

        tip = "✅ 已获取二维码。请用微信扫码并确认登录。"
        if exp:
            try:
                exp_i = int(exp)
                if exp_i > 1_000_000_000:
                    left = exp_i - int(time.time())
                    tip += f"（二维码剩余：{_fmt_seconds_left(left)}）"
            except Exception:
                pass

        return qr or "", fw or "", tip

    def admin_qr_check(tmp_token: str):
        t = (tmp_token or "").strip()
        if not t:
            return "⚠️ 临时 frameworkToken 为空，先点击“获取二维码”"

        j = request_service.api_wechat_status(t)
        if not isinstance(j, dict):
            return "❌ status 返回非 dict"

        msg = j.get("msg") or j.get("message") or ""
        data = j.get("data") if isinstance(j.get("data"), dict) else None
        has_openid = j.get("hasOpenId")
        if has_openid is None and data:
            has_openid = data.get("hasOpenId")

        if j.get("success") is True or has_openid is True:
            return "✅ 扫码已完成（已拿到登录态）。点击“保存为当前 frameworkToken”。"
        if data and ("openid" in data or "openId" in data or "access_token" in data or "accessToken" in data):
            return "✅ 扫码已完成（data 中已包含登录态字段）。点击“保存为当前 frameworkToken”。"
        if j.get("code") in (0, "0") and isinstance(msg, str) and any(k in msg for k in ["成功", "已登录", "已扫码", "完成"]):
            return "✅ 扫码已完成。点击“保存为当前 frameworkToken”。"
        return f"⏳ 尚未完成：{msg or j}"

    def admin_qr_apply(tmp_token: str):
        t = (tmp_token or "").strip()
        if not t:
            return gr.update(value=""), "⚠️ 临时 frameworkToken 为空"
        try:
            _save_framework_token(t)
        except Exception as e:
            return gr.update(value=""), f"❌ 保存失败：{e}"

        st = request_service.ensure_framework_token_valid(
            t,
            refresh_interval_sec=0,
            cache_ttl_sec=0,
        )
        if st.get("need_reauth"):
            return gr.update(value=t), f"⚠️ 已保存，但当前 token 可能不可用：{st.get('message')}"
        return gr.update(value=t), "✅ 已保存并校验完成"

    def tick_framework_token_guard():
        interval = 90 * 60
        st = request_service.ensure_framework_token_valid(
            refresh_interval_sec=interval,
            cache_ttl_sec=10 * 60,
        )

        # ✅ seconds_left 现在多数情况为 None，就显示“距下次刷新”
        try:
            meta = request_service._meta_load()  # 如果你不想用私有函数，就看下面“更规范方案”
            last_refresh = int(meta.get("refreshed_at") or 0)
        except Exception:
            last_refresh = 0

        if last_refresh > 0:
            left = interval - (int(time.time()) - last_refresh)
            if left < 0:
                left = 0
            s_left = f"下次刷新：{_fmt_seconds_left(left)}"
        else:
            s_left = "下次刷新：未知（未记录 refreshed_at）"

        flag = []
        if st.get("did_refresh"):
            flag.append("已 refresh")
        if st.get("need_reauth"):
            flag.append("需要扫码")
        tag = ("（" + " / ".join(flag) + "）") if flag else ""

        return gr.update(value=f"{st.get('message')} | {s_left}{tag}")


    # ======================
    # UI 组装
    # ======================
    init_rows, init_meta = make_log_table_meta(20)

    with gr.Blocks() as demo:
        gr.HTML("<div id='main-container'>")

        reserve_raw_state = gr.State("无")
        up_coin_state = gr.State(None)
        down_coin_state = gr.State(None)
        log_meta_state = gr.State(init_meta)
        last_day_state = gr.State(_today_key())

        egg_played_state = gr.State(False)
        egg_js_tick_state = gr.State(0)  # dummy：保证 js then 稳定触发

        page1, w1 = home_mod.build(init_rows)
        page2, w2 = settlement.build()
        page3, w3 = confirm.build()
        page4, w4 = picker.build()
        page5, w5 = log_detail.build()
        page6, w6 = logs_more.build(init_rows)
        page7, w7 = reserve_manager.build()

        midnight_timer = gr.Timer(60)
        token_guard_timer = gr.Timer(600)

        gr.HTML("</div>")

        midnight_timer.tick(fn=tick_midnight_refresh, inputs=[last_day_state], outputs=[last_day_state, w1["stats"]])
        demo.load(fn=lambda: gr.update(value=home_stats_text()), outputs=[w1["stats"]])
        demo.load(fn=refresh_logs_and_stats, outputs=[w1["log_table"], log_meta_state, w1["stats"]])
        token_guard_timer.tick(fn=tick_framework_token_guard, outputs=[w1["admin_fw_status"]])

        # ====== 管理员绑定（原样）======
        w1["btn_admin"].click(fn=admin_open, outputs=[
            w1["admin_panel"], w1["admin_user"], w1["admin_pass"], w1["admin_login_status"], w1["admin_edit_panel"],
            w1["admin_current"], w1["admin_new_total"], w1["admin_save_status"],
            w1["admin_fw_token"], w1["admin_fw_status"],
            w1["admin_qr_url"], w1["admin_qr_tmp_token"], w1["admin_qr_status"],
        ])
        w1["btn_admin_close"].click(fn=admin_close, outputs=[
            w1["admin_panel"], w1["admin_user"], w1["admin_pass"], w1["admin_login_status"], w1["admin_edit_panel"],
            w1["admin_current"], w1["admin_new_total"], w1["admin_save_status"],
            w1["admin_fw_token"], w1["admin_fw_status"],
            w1["admin_qr_url"], w1["admin_qr_tmp_token"], w1["admin_qr_status"],
        ])
        w1["btn_admin_login"].click(fn=admin_login, inputs=[w1["admin_user"], w1["admin_pass"]], outputs=[
            w1["admin_login_status"], w1["admin_edit_panel"],
            w1["admin_current"], w1["admin_new_total"], w1["admin_save_status"],
            w1["admin_fw_token"], w1["admin_fw_status"],
            w1["admin_qr_url"], w1["admin_qr_tmp_token"], w1["admin_qr_status"],
        ])
        w1["btn_admin_save"].click(fn=admin_save, inputs=[w1["admin_new_total"]], outputs=[
            w1["admin_current"], w1["admin_new_total"], w1["admin_save_status"], w1["stats"]
        ])
        w1["btn_admin_fw_save"].click(fn=admin_fw_save, inputs=[w1["admin_fw_token"]],
                                      outputs=[w1["admin_fw_token"], w1["admin_fw_status"]])
        w1["btn_admin_fw_reload"].click(fn=admin_fw_reload, outputs=[w1["admin_fw_token"], w1["admin_fw_status"]])
        w1["btn_admin_qr_get"].click(fn=admin_qr_get, outputs=[w1["admin_qr_url"], w1["admin_qr_tmp_token"], w1["admin_qr_status"]])
        w1["btn_admin_qr_check"].click(fn=admin_qr_check, inputs=[w1["admin_qr_tmp_token"]], outputs=[w1["admin_qr_status"]])
        w1["btn_admin_qr_apply"].click(fn=admin_qr_apply, inputs=[w1["admin_qr_tmp_token"]],
                                       outputs=[w1["admin_fw_token"], w1["admin_fw_status"]])

        # ====== Home -> Settlement：恢复原重置逻辑 + 重置本轮彩蛋 ======
        w1["btn_settlement"].click(
            fn=goto_settlement,
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        ).then(
            fn=settlement.reset_settlement_ui,
            outputs=[
                w2["img_up"],
                w2["img_down"],
                up_coin_state,
                down_coin_state,
                w2["up_coin_preview"],
                w2["down_coin_preview"],
                w2["up_fail_hint"],
                w2["down_fail_hint"],
                w2["up_hint_img"],
                w2["down_hint_img"],
            ],
        ).then(
            fn=lambda: False,
            outputs=[egg_played_state],
        ).then(
            fn=lambda: (gr.update(value=""), 0),
            outputs=[w1["egg_audio_data"], egg_js_tick_state],
        ).then(
            fn=_tick,
            inputs=[egg_js_tick_state],
            outputs=[egg_js_tick_state],
            js=r"""
(x) => {
  try{
    const btn = document.getElementById("egg-play-btn");
    if(btn) btn.style.display = "none";
  }catch(e){}
  return x;
}
""",
        )

        w2["btn_back_home"].click(fn=back_to_home, outputs=[page1, page2, page3, page4, page5, page6, page7])

        w2["img_up"].change(fn=ocr_preview, inputs=w2["img_up"],
                            outputs=[up_coin_state, w2["up_coin_preview"], w2["up_fail_hint"], w2["up_hint_img"]])
        w2["img_down"].change(fn=ocr_preview, inputs=w2["img_down"],
                              outputs=[down_coin_state, w2["down_coin_preview"], w2["down_fail_hint"], w2["down_hint_img"]])

        w2["btn_submit"].click(
            fn=submit_with_ocr,
            inputs=[w2["img_up"], w2["img_down"], up_coin_state, down_coin_state, reserve_raw_state],
            outputs=[w3["confirm_text"], w3["btn_confirm"], w3["remark"],
                     page1, page2, page3, page4, page5, page6, page7],
        )

        w3["btn_cancel"].click(fn=back_to_settlement, outputs=[page1, page2, page3, page4, page5, page6, page7])

        _RE_YUAN = re.compile(r"本次折合(?:\s*[:：])?\s*([0-9]+(?:\.[0-9]+)?)\s*元")

        def on_confirm_write_log(img_up_path, img_down_path, confirm_text, remark):
            logs_service.save_submit_log(
                up_img_path=img_up_path,
                down_img_path=img_down_path,
                log_text=confirm_text,
                remark=remark or "",
            )
            try:
                m = _RE_YUAN.search(confirm_text or "")
                if m:
                    yuan = float(m.group(1))
                    finance_service.deduct_prepayment(yuan)
            except Exception:
                pass
            return back_to_home()

        w3["btn_confirm"].click(
            fn=on_confirm_write_log,
            inputs=[w2["img_up"], w2["img_down"], w3["confirm_text"], w3["remark"]],
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        ).then(
            fn=refresh_after_confirm_and_pick_audio,
            inputs=[egg_played_state],
            outputs=[
                w1["log_table"],
                log_meta_state,
                w1["stats"],
                w1["egg_audio_data"],
                egg_js_tick_state,
                egg_played_state,
            ],
        ).then(
            fn=_tick,
            inputs=[egg_js_tick_state],
            outputs=[egg_js_tick_state],
            js=r"""
(x) => {
  try{
    const box = document.getElementById("egg-audio-data");
    const btn = document.getElementById("egg-play-btn");

    if(btn){
      btn.style.display = "none";
      btn.innerText = "🔊 播放彩蛋";
    }

    if(!box){
      if(btn){
        btn.style.display = "block";
        btn.innerText = "🔊 没找到播放器数据（刷新重试）";
      }
      return x;
    }

    const inp = box.querySelector("textarea, input");
    const data = inp ? (inp.value || "") : "";

    console.log("[egg] auto data len =", data.length);

    if(!data || !data.startsWith("data:audio/")){
      if(btn){
        btn.style.display = "block";
        btn.innerText = "🔊 还没加载好（再点一次）";
      }
      return x;
    }

    window.__eggAudio = new Audio(data);
    window.__eggAudio.currentTime = 0;

    window.__eggAudio.play().then(() => {
      if(btn) btn.style.display = "none";
    }).catch((e) => {
      console.log("[egg] auto play rejected:", e);
      if(btn){
        btn.style.display = "block";
        btn.innerText = "🔊 播放失败（点我重试）";
      }
    });
  }catch(e){
    console.log("[egg] auto error:", e);
    const btn = document.getElementById("egg-play-btn");
    if(btn){
      btn.style.display = "block";
      btn.innerText = "🔊 播放异常（点我重试）";
    }
  }
  return x;
}
""",
        )

        w1["egg_play_btn"].click(
            fn=_tick,
            inputs=[egg_js_tick_state],
            outputs=[egg_js_tick_state],
            js=r"""
(x) => {
  try{
    const box = document.getElementById("egg-audio-data");
    const btn = document.getElementById("egg-play-btn");

    if(!box){
      if(btn){
        btn.style.display = "block";
        btn.innerText = "🔊 没找到播放器数据（刷新重试）";
      }
      return x;
    }

    const inp = box.querySelector("textarea, input");
    const data = inp ? (inp.value || "") : "";

    console.log("[egg] click data len =", data.length);

    if(!data || !data.startsWith("data:audio/")){
      if(btn){
        btn.style.display = "block";
        btn.innerText = "🔊 还没加载好（再点一次）";
      }
      return x;
    }

    if(btn){
      btn.style.display = "block";
      btn.innerText = "🔊 正在播放…";
    }

    window.__eggAudio = new Audio(data);
    window.__eggAudio.currentTime = 0;

    window.__eggAudio.play().then(() => {
      if(btn) btn.style.display = "none";
    }).catch((e) => {
      console.log("[egg] click play rejected:", e);
      if(btn){
        btn.style.display = "block";
        btn.innerText = "🔊 播放失败（点我重试）";
      }
    });
  }catch(e){
    console.log("[egg] click error:", e);
    const btn = document.getElementById("egg-play-btn");
    if(btn){
      btn.style.display = "block";
      btn.innerText = "🔊 播放异常（点我重试）";
    }
  }
  return x;
}
""",
        )

        # ====== 后续逻辑保持原样 ======
        w2["btn_manage_reserve"].click(
            fn=goto_reserve_manager,
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        ).then(
            fn=lambda: gr.update(value=""),
            outputs=[w7["result_box"]],
        )

        w7["btn_confirm"].click(fn=reserve_manager.calc_from_text, inputs=[w7["input_box"]], outputs=[w7["result_box"]])

        w7["btn_apply"].click(
            fn=reserve_manager.build_settlement_summary,
            inputs=[w7["result_box"]],
            outputs=[reserve_raw_state],
        ).then(
            fn=format_reserve_expr_for_settlement,
            inputs=[reserve_raw_state],
            outputs=[w2["reserve_total_text"]],
        ).then(
            fn=lambda: gr.update(value=""),
            outputs=[w2["reserve_total_hint"]],
        ).then(
            fn=back_from_reserve_manager,
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        )

        w7["btn_mgr_back"].click(fn=back_from_reserve_manager, outputs=[page1, page2, page3, page4, page5, page6, page7])

        w1["btn_refresh_logs"].click(fn=refresh_logs_and_stats, outputs=[w1["log_table"], log_meta_state, w1["stats"]])

        w1["log_table"].select(
            fn=log_detail.open_log_detail,
            inputs=[log_meta_state],
            outputs=[w5["log_detail_text"], w5["img_up"], w5["img_down"]],
        ).then(
            fn=lambda: show_pages(False, False, False, False, True, False, False),
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        )

        w5["btn_log_ok"].click(fn=back_from_log_detail, outputs=[page1, page2, page3, page4, page5, page6, page7])

        w1["btn_more"].click(
            fn=logs_more.open_more_page,
            outputs=[w6["more_table"], w6["more_info"], w6["more_page_state"], w6["more_meta_state"]],
        ).then(
            fn=lambda: show_pages(False, False, False, False, False, True, False),
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        )

        w6["btn_prev"].click(fn=logs_more.more_prev, inputs=[w6["more_page_state"]],
                             outputs=[w6["more_table"], w6["more_info"], w6["more_page_state"], w6["more_meta_state"]])
        w6["btn_next"].click(fn=logs_more.more_next, inputs=[w6["more_page_state"]],
                             outputs=[w6["more_table"], w6["more_info"], w6["more_page_state"], w6["more_meta_state"]])

        w6["more_table"].select(
            fn=log_detail.open_log_detail,
            inputs=[w6["more_meta_state"]],
            outputs=[w5["log_detail_text"], w5["img_up"], w5["img_down"]],
        ).then(
            fn=lambda: show_pages(False, False, False, False, True, False, False),
            outputs=[page1, page2, page3, page4, page5, page6, page7],
        )

        w6["btn_more_back"].click(fn=back_to_home, outputs=[page1, page2, page3, page4, page5, page6, page7])

    return demo
