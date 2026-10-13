# tools/wechat_login_full.py
import os
import time
import json
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# =======================
# 配置
# =======================
API_BASE = os.getenv("DF_API_BASE", "https://df-api.shallow.ink")
API_KEY = os.getenv("DF_API_KEY", "")  # setx DF_API_KEY "sk-xxxx"
TIMEOUT = (6, 25)  # (connect, read)

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_FILE = DATA_DIR / "frameworkToken"


# =======================
# HTTP 工具
# =======================
def _pretty(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, indent=2)


def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def _headers() -> Dict[str, str]:
    h = {
        "Accept": "application/json",
        "User-Agent": "delta-trade-app/1.0",
    }
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def _get(session: requests.Session, path: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    url = f"{API_BASE}{path}"
    r = session.get(url, params=params or {}, headers=_headers(), timeout=TIMEOUT)
    # 接口很多时候 status=200 但 code!=0，所以这里不 raise_for_status
    try:
        return {"_http": r.status_code, "_url": r.url, "_headers": dict(r.headers), **r.json()}
    except Exception:
        return {"_http": r.status_code, "_url": r.url, "_headers": dict(r.headers), "_raw": r.text}


# =======================
# API：扫码登录流程
# =======================
def api_wechat_qr(session: requests.Session) -> Dict[str, Any]:
    """
    GET /login/wechat/qr
    你实际返回示例：
    {
      "code": 0,
      "msg": "ok",
      "frameworkToken": "...",
      "qr_image": "https://open.weixin.qq.com/connect/qrcode/....",
      "expire": 1770...
    }
    """
    return _get(session, "/login/wechat/qr")


def api_wechat_status(session: requests.Session, framework_token: str) -> Dict[str, Any]:
    """
    GET /login/wechat/status?token=frameworkToken
    """
    return _get(session, "/login/wechat/status", params={"frameworkToken": framework_token})


def api_wechat_token(session: requests.Session, framework_token: str) -> Dict[str, Any]:
    """
    GET /login/wechat/token?token=frameworkToken
    获取微信登录成功后的访问令牌信息
    """
    return _get(session, "/login/wechat/token", params={"token": framework_token})


def api_wechat_refresh(session: requests.Session, framework_token: str) -> Dict[str, Any]:
    """
    GET /login/wechat/refresh?frameworkToken=xxx
    PRO：刷新登录状态与访问令牌
    """
    return _get(session, "/login/wechat/refresh", params={"frameworkToken": framework_token})


# =======================
# 业务：执行整套流程
# =======================
def save_framework_token(token: str) -> None:
    TOKEN_FILE.write_text(token.strip(), encoding="utf-8")
    print(f"✅ 已保存 frameworkToken 到: {TOKEN_FILE.resolve()}")


def wait_for_scan(session: requests.Session, framework_token: str, timeout_sec: int = 180, interval_sec: int = 2) -> Dict[str, Any]:
    """
    轮询 /login/wechat/status 直到扫码完成
    不同后端返回字段可能不同，所以这里用“尽量宽松”的判定：
    - success==True 或 code==0 且 msg/状态提示表明完成
    - 或者后端返回 data/openid/hasOpenId 等字段
    """
    print("\n开始轮询扫码状态：/login/wechat/status?token=frameworkToken")
    t0 = time.time()

    last = None
    while time.time() - t0 < timeout_sec:
        j = api_wechat_status(session, framework_token)
        last = j

        http = j.get("_http")
        code = j.get("code")
        msg = j.get("msg") or j.get("message")
        success = j.get("success")
        data = j.get("data") if isinstance(j.get("data"), dict) else None

        # 常见“完成”信号
        has_openid = None
        if isinstance(j, dict):
            has_openid = j.get("hasOpenId")
            if has_openid is None and data:
                has_openid = data.get("hasOpenId")

        print(f"[poll] http={http} code={code} success={success} hasOpenId={has_openid} msg={msg}")

        # 判定完成（尽量保守：看到明确成功/拿到openid/hasOpenId=True）
        if success is True:
            return j
        if has_openid is True:
            return j
        if data and ("openid" in data or "openId" in data or "access_token" in data or "accessToken" in data):
            return j
        # 某些实现 code==0 且 msg 提示“已扫码/已登录”
        if code == 0 and isinstance(msg, str) and any(k in msg for k in ["成功", "已登录", "已扫码", "完成"]):
            return j

        time.sleep(interval_sec)

    raise TimeoutError(f"❌ 轮询超时（{timeout_sec}s），二维码可能过期。最后一次返回：\n{_pretty(last)}")


def main():
    print("API_BASE:", API_BASE)
    print("API_KEY:", "已设置" if API_KEY else "未设置（部分接口可能受限）")

    s = _make_session()

    # 1) 获取二维码
    qr = api_wechat_qr(s)
    print("\n=== /login/wechat/qr 返回 ===")
    print(_pretty(qr))

    if qr.get("code") != 0:
        raise RuntimeError(f"❌ 获取二维码失败：{qr.get('msg') or qr.get('message') or qr}")

    framework_token = qr.get("frameworkToken")
    qr_image = qr.get("qr_image") or qr.get("qrImage") or qr.get("qr")

    if not framework_token or not qr_image:
        raise RuntimeError(f"❌ 缺少 frameworkToken 或 qr_image：\n{_pretty(qr)}")

    print("\n==== 请扫码 ====")
    print("二维码链接（用微信打开/扫码）：", qr_image)
    print("frameworkToken：", framework_token)

    # 2) 轮询扫码状态
    print("\n请在微信里确认登录，然后回来看控制台输出。")
    status = wait_for_scan(s, framework_token, timeout_sec=180, interval_sec=2)

    print("\n=== 扫码状态完成（/login/wechat/status）===")
    print(_pretty(status))

    # 3) 查询 token 信息（访问令牌）
    token_info = api_wechat_token(s, framework_token)
    print("\n=== /login/wechat/token 返回 ===")
    print(_pretty(token_info))

    # 4) 保存 frameworkToken
    save_framework_token(framework_token)

    # 5) 尝试 refresh（PRO）
    refresh = api_wechat_refresh(s, framework_token)
    print("\n=== /login/wechat/refresh 返回 ===")
    print(_pretty(refresh))

    print("\n✅ 流程结束：qr -> status -> token -> save -> refresh")


if __name__ == "__main__":
    main()
