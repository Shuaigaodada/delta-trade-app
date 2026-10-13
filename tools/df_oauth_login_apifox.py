from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

DF_BASE = os.environ.get("DF_BASE", "https://df-api-eo.shallow.ink").strip()
API_KEY = os.environ.get("DF_API_KEY", "").strip()

OAUTH_GET_URL = f"{DF_BASE}/login/wechat/oauth"
OAUTH_POST_URL = f"{DF_BASE}/login/wechat/oauth"
OAUTH_STATUS_URL = f"{DF_BASE}/login/wechat/oauth/status"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

FRAMEWORK_TOKEN_FILE = DATA_DIR / "frameworkToken"
COOKIE_FILE = DATA_DIR / "cookies"


def save_json(name: str, obj: Any) -> None:
    (DATA_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_ascii_visible(s: str) -> str:
    return "".join(ch for ch in s.strip() if 32 <= ord(ch) <= 126)


def extract_code(url_or_code: str) -> str:
    s = url_or_code.strip()
    if re.fullmatch(r"[0-9A-Za-z_\-]{6,256}", s):
        return s
    m = re.search(r"[?&]code=([^&]+)", s)
    if m:
        return m.group(1)
    raise ValueError("没找到 code，请粘贴回调URL或 code")


def pick_str(d: Any, *keys: str) -> Optional[str]:
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    data = d.get("data")
    if isinstance(data, dict):
        for k in keys:
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def try_extract_cookie_like(obj: Any) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    for k in ("cookie", "ck", "amsCookie", "ams_cookie", "setCookie", "cookieStr", "cookie_str"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    data = obj.get("data")
    if isinstance(data, dict):
        for k in ("cookie", "ck", "amsCookie", "ams_cookie", "setCookie", "cookieStr", "cookie_str"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def main() -> None:
    if not API_KEY:
        raise RuntimeError("请先设置环境变量 DF_API_KEY，比如：$env:DF_API_KEY='sk-xxxx'")

    headers = {
        "Authorization": "Bearer " + clean_ascii_visible(API_KEY),
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    s = requests.Session()

    # 1) GET oauth info（参数不重要就先不带，避免干扰）
    r1 = s.get(OAUTH_GET_URL, headers=headers, timeout=20)
    r1.raise_for_status()
    j1 = r1.json()
    save_json("debug_apifox_1_get_oauth.json", {"status": r1.status_code, "headers": dict(r1.headers), "data": j1})

    framework_token = pick_str(j1, "frameworkToken")
    login_url = pick_str(j1, "login_url", "loginUrl", "url", "authUrl")
    if not framework_token or not login_url:
        raise RuntimeError("GET /login/wechat/oauth 没拿到 frameworkToken/login_url")

    FRAMEWORK_TOKEN_FILE.write_text(framework_token, encoding="utf-8")

    print("\n打开授权链接：\n", login_url)
    cb = input("\n粘贴回调URL或 code：")
    code = extract_code(cb)

    # 2) POST 用正确字段：code（不是 authcode）
    payload = {"frameworkToken": framework_token, "code": code}

    # 指数退避重试：解决“访问人数太多/系统繁忙”
    max_try = 10
    delay = 2.0
    last_post = None

    print("\n[提交] POST /login/wechat/oauth (frameworkToken + code)，失败会自动重试...\n")
    for i in range(1, max_try + 1):
        rp = s.post(
            OAUTH_POST_URL,
            headers={**headers, "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30,
        )
        try:
            jp = rp.json()
        except Exception:
            jp = {"raw": rp.text}

        last_post = {"status": rp.status_code, "payload": payload, "data": jp, "headers": dict(rp.headers)}
        save_json(f"debug_apifox_2_post_try_{i}.json", last_post)

        msg = pick_str(jp, "msg") or ""
        code_ret = None
        if isinstance(jp, dict):
            code_ret = jp.get("code")
            if code_ret is None and isinstance(jp.get("data"), dict):
                code_ret = jp["data"].get("code")

        print(f"try {i}/{max_try}: code={code_ret} msg={msg}")

        # 成功判定：code==0 且不是“AccessToken获取失败”
        if (code_ret == 0) and ("AccessToken获取失败" not in msg) and ("访问人数太多" not in msg):
            break

        if i < max_try:
            time.sleep(delay)
            delay = min(delay * 2, 30.0)

    # 3) 轮询 status，拿 cookie / 凭证
    print("\n[轮询] GET /login/wechat/oauth/status（最多 60 秒）...")
    last_status = None
    for i in range(60):
        time.sleep(1)
        rs = s.get(OAUTH_STATUS_URL, headers=headers, params={"frameworkToken": framework_token}, timeout=20)
        try:
            js = rs.json()
        except Exception:
            js = {"raw": rs.text}

        last_status = {"status": rs.status_code, "data": js, "headers": dict(rs.headers)}
        save_json(f"debug_apifox_3_status_poll_{i+1}.json", last_status)

        d = js.get("data", js) if isinstance(js, dict) else {}
        status = d.get("status")
        wx_code = d.get("wx_code")
        msg = d.get("msg") or d.get("message") or ""
        print(f"  - poll {i+1}/60: status={status} wx_code={wx_code} msg={msg}")

        ck = try_extract_cookie_like(js)
        if ck:
            COOKIE_FILE.write_text(ck, encoding="utf-8")
            print("\n✅ 已从 status 返回写入 cookie：data/cookies")
            return

        # 如果 wx_code 出现非空，也算重大进展（说明服务端拿到了）
        if isinstance(wx_code, str) and wx_code.strip():
            print("\n✅ status 已拿到 wx_code（非空）。请把 data/debug_apifox_3_status_poll_*.json 贴我，我来继续把它换成 DF cookie。")
            return

    print("\n❌ 仍未拿到 cookie / wx_code。")
    print("你可以把这两个文件贴我（敏感值可打码）：")
    print("  - data/debug_apifox_2_post_try_*.json（最后一次）")
    print("  - data/debug_apifox_3_status_poll_60.json")


if __name__ == "__main__":
    main()
