import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests

DF_BASE = "https://df-api-eo.shallow.ink"
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# PowerShell:
#   $env:DF_API_KEY="sk-xxxx"
API_KEY = os.environ.get("DF_API_KEY", "").strip()

WECHAT_QR_URL = f"{DF_BASE}/login/wechat/qr"
WECHAT_REFRESH_URL = f"{DF_BASE}/login/wechat/refresh"

# 你刚验证：这个其实是“状态接口”
WECHAT_TOKEN_STATUS_URL = f"{DF_BASE}/login/wechat/token"

# 你提供的 OAuth 信息接口
WECHAT_OAUTH_INFO_URL = f"{DF_BASE}/login/wechat/oauth"

FRAMEWORK_TOKEN_FILE = DATA_DIR / "frameworkToken"
COOKIE_FILE = DATA_DIR / "cookies"

def clean_ascii_visible(s: str) -> str:
    return "".join(ch for ch in s.strip() if 32 <= ord(ch) <= 126)

def save_text(path: Path, text: str) -> None:
    path.write_text(text.strip(), encoding="utf-8")

def save_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def extract_framework_token(j: Any) -> Optional[str]:
    if isinstance(j, dict) and isinstance(j.get("frameworkToken"), str):
        return j["frameworkToken"].strip()
    if isinstance(j, dict) and isinstance(j.get("data"), dict):
        v = j["data"].get("frameworkToken")
        if isinstance(v, str):
            return v.strip()
    return None

def extract_qr_link(j: Any) -> Optional[str]:
    if not isinstance(j, dict):
        return None
    for k in ("qr_image", "qrUrl", "qrcodeUrl", "qrcode", "url", "authUrl", "loginUrl"):
        v = j.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if isinstance(j.get("data"), dict):
        for k in ("qr_image", "qrUrl", "qrcodeUrl", "qrcode", "url", "authUrl", "loginUrl"):
            v = j["data"].get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None

def main():
    if not API_KEY:
        raise RuntimeError("请设置环境变量 DF_API_KEY，例如：$env:DF_API_KEY='sk-xxxx'")

    key = clean_ascii_visible(API_KEY)
    headers = {
        "Authorization": "Bearer " + key,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    s = requests.Session()

    # 1) 获取二维码
    r = s.get(WECHAT_QR_URL, headers=headers, timeout=20)
    r.raise_for_status()
    qr_json = r.json()
    save_json(DATA_DIR / "debug_1_qr.json", qr_json)

    ft = extract_framework_token(qr_json)
    if not ft:
        raise RuntimeError("qr 返回没 frameworkToken，已保存 data/debug_1_qr.json")

    save_text(FRAMEWORK_TOKEN_FILE, ft)
    print("[OK] frameworkToken ->", FRAMEWORK_TOKEN_FILE)

    qr_link = extract_qr_link(qr_json)
    if qr_link:
        print("\n[扫码地址] 复制到浏览器打开，用微信扫一扫：")
        print(qr_link)
    else:
        print("\n[提示] 没解析出二维码地址，看 data/debug_1_qr.json")

    input("\n扫码授权完成后按回车继续…")

    # 2) refresh
    rr = s.get(WECHAT_REFRESH_URL, headers=headers, params={"frameworkToken": ft}, timeout=20)
    rr.raise_for_status()
    refresh_json = rr.json() if rr.text else {}
    save_json(DATA_DIR / "debug_2_refresh.json", refresh_json)

    # 3) token 状态（你当前这个）
    rt = s.get(WECHAT_TOKEN_STATUS_URL, headers=headers, params={"frameworkToken": ft}, timeout=20)
    rt.raise_for_status()
    token_status_json = rt.json() if rt.text else {}
    save_json(DATA_DIR / "debug_3_token_status.json", token_status_json)

    print("[token-status] ", token_status_json)

    # 4) 关键：尝试拉 OAuth 用户信息（拿 openid / 用户资料 / 可能的 cookie）
    # 先用 frameworkToken 当 query 试试（很多后端会这么设计）
    ro = s.get(WECHAT_OAUTH_INFO_URL, headers=headers, params={"frameworkToken": ft}, timeout=20)
    # 这里不直接 raise，先保存，方便看错误
    try:
        oauth_json = ro.json()
    except Exception:
        oauth_json = {"raw": ro.text}

    save_json(DATA_DIR / "debug_4_oauth_info.json", {"status": ro.status_code, "data": oauth_json})
    print("[oauth-info] status:", ro.status_code)
    print("[oauth-info] 已保存 data/debug_4_oauth_info.json")

    print("\n下一步：打开 data/debug_4_oauth_info.json 看它到底返回了什么。")
    print("如果里面出现 openid/access_token/refresh_token/cookie 等字段，我们就能继续写自动拿 AMS cookie 的逻辑。")

if __name__ == "__main__":
    main()
