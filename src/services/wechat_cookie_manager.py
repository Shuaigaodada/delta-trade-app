from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests


# =========================
# 可配置项（先按你说的“写死”）
# =========================
DF_BASE = "https://df-api-eo.shallow.ink"

# ⚠️ 建议你自己填：Bearer sk-xxxx（不要提交到仓库）
API_KEY = "sk-UjhpQv7IuyiYOf91qHLaout1O3okryMs"

# 文档已确认：
# GET /login/wechat/refresh?frameworkToken=xxxx
WECHAT_REFRESH_URL = f"{DF_BASE}/login/wechat/refresh"

# 文档已确认：
# GET /login/wechat/token?token=frameworkToken
WECHAT_TOKEN_URL = f"{DF_BASE}/login/wechat/token"

# frameworkToken：你扫码登录成功后获得一次，建议存到 data/frameworkToken
FRAMEWORK_TOKEN_FILE = Path("data") / "frameworkToken"

# 你业务要用的 cookie：存到 data/cookies
COOKIE_FILE = Path("data") / "cookies"


# =========================
# 工具函数
# =========================
def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text((s or "").strip(), encoding="utf-8")


def _merge_cookie_kv(existing_cookie: str, new_cookie: str) -> str:
    """
    合并两段 cookie 字符串（都按 "k=v; k2=v2" 形式解析）。
    new_cookie 优先覆盖 existing_cookie 的同名 key。
    """
    def parse(cookie_str: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not cookie_str:
            return out
        for part in cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k:
                out[k] = v
        return out

    old_map = parse(existing_cookie)
    new_map = parse(new_cookie)
    old_map.update(new_map)

    # 保持输出稳定：按 key 排序（也可以不排序）
    return "; ".join([f"{k}={v}" for k, v in sorted(old_map.items())])


def _extract_cookie_from_json(obj: Any) -> Optional[str]:
    """
    从 JSON 里尝试提取 cookie（接口文档没写返回结构，做容错）
    """
    if not isinstance(obj, dict):
        return None

    # 常见直接字段
    for k in ("cookie", "ck", "amsCookie", "ams_cookie", "setCookie"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # 常见 data 包裹
    data = obj.get("data")
    if isinstance(data, dict):
        for k in ("cookie", "ck", "amsCookie", "ams_cookie", "setCookie"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    return None


def _cookiejar_to_str(jar: requests.cookies.RequestsCookieJar) -> str:
    """
    把 requests 的 cookiejar 转成 "k=v; k2=v2"
    """
    pairs = []
    for c in jar:
        if c.name and c.value is not None:
            pairs.append(f"{c.name}={c.value}")
    return "; ".join(pairs)


# =========================
# 核心：Cookie 管理器
# =========================
@dataclass
class CookieManagerConfig:
    api_key: str
    refresh_url: str
    token_url: str
    cookie_file: Path = COOKIE_FILE
    framework_token_file: Path = FRAMEWORK_TOKEN_FILE

    # 判断“业务响应是否过期”的函数（可选）
    is_expired: Optional[Callable[[requests.Response], bool]] = None


class WechatCookieManager:
    """
    用 shallow.ink 的微信登录体系自动刷新 cookie

    刷新闭环：
      1) GET /login/wechat/refresh?frameworkToken=xxx
      2) GET /login/wechat/token?token=xxx
      3) 从响应 JSON 或响应 cookies 里提取 cookie，写入 data/cookies
    """

    def __init__(self, cfg: CookieManagerConfig, session: Optional[requests.Session] = None):
        self.cfg = cfg
        self.s = session or requests.Session()

    # ---------- 基础读写 ----------
    def get_cookie(self) -> str:
        return _read_text(self.cfg.cookie_file)

    def set_cookie(self, cookie: str) -> None:
        _write_text(self.cfg.cookie_file, cookie)

    def get_framework_token(self) -> str:
        ft = _read_text(self.cfg.framework_token_file)
        if not ft:
            raise RuntimeError(
                f"缺少 frameworkToken。请把 frameworkToken 写入 {self.cfg.framework_token_file}（纯文本一行）。"
            )
        return ft

    def set_framework_token(self, ft: str) -> None:
        _write_text(self.cfg.framework_token_file, ft)

    def _auth_headers(self) -> Dict[str, str]:
        if not self.cfg.api_key or self.cfg.api_key == "YOUR_API_KEY_HERE":
            raise RuntimeError("缺少 API_KEY：请在代码顶部把 API_KEY 填好（或改成从环境变量读取）。")
        return {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        }

    # ---------- 刷新流程 ----------
    def refresh(self) -> str:
        """
        刷新微信登录态并更新 cookie。
        返回最终 cookie 字符串。
        """
        ft = self.get_framework_token()

        # Step 1: refresh（续命登录态）
        r1 = self.s.get(
            self.cfg.refresh_url,
            headers=self._auth_headers(),
            params={"frameworkToken": ft},
            timeout=20,
        )
        r1.raise_for_status()

        cookie = self.get_cookie()

        # 先合并 r1 的 cookies（requests 已解析 Set-Cookie）
        r1_cookie_str = _cookiejar_to_str(r1.cookies)
        if r1_cookie_str:
            cookie = _merge_cookie_kv(cookie, r1_cookie_str)

        # 再尝试从 r1 的 JSON 直接拿 cookie（如果有）
        try:
            j1 = r1.json()
        except Exception:
            j1 = None
        c1 = _extract_cookie_from_json(j1)
        if c1:
            cookie = _merge_cookie_kv(cookie, c1)

        # Step 2: token query（文档确认：参数名是 token）
        r2 = self.s.get(
            self.cfg.token_url,
            headers=self._auth_headers(),
            params={"token": ft},  # ✅ 关键修复：这里必须是 token
            timeout=20,
        )
        r2.raise_for_status()

        # 合并 r2 cookies
        r2_cookie_str = _cookiejar_to_str(r2.cookies)
        if r2_cookie_str:
            cookie = _merge_cookie_kv(cookie, r2_cookie_str)

        # 再从 r2 JSON 尝试提取 cookie（更可能在这里返回）
        try:
            j2 = r2.json()
        except Exception:
            j2 = None
        c2 = _extract_cookie_from_json(j2)
        if c2:
            cookie = _merge_cookie_kv(cookie, c2)

        cookie = (cookie or "").strip()
        if not cookie:
            raise RuntimeError(
                "刷新完成但仍未获得 cookie。\n"
                "建议你把 /login/wechat/token 的返回 JSON 发我，我可以把 cookie 提取规则改成完全匹配。"
            )

        self.set_cookie(cookie)
        return cookie

    # ---------- 自动重试封装 ----------
    def request_with_auto_refresh(
        self,
        make_request: Callable[[str], requests.Response],
        max_retry: int = 1,
    ) -> requests.Response:
        """
        make_request(cookie_str) -> Response
        若响应判定为过期，则 refresh() 后重试一次
        """
        cookie = self.get_cookie()
        resp = make_request(cookie)

        if self._is_expired(resp) and max_retry > 0:
            self.refresh()
            cookie = self.get_cookie()
            resp = make_request(cookie)

        return resp

    def _is_expired(self, resp: requests.Response) -> bool:
        # 用户自定义优先
        if self.cfg.is_expired:
            return self.cfg.is_expired(resp)

        # 默认策略：尝试解析 json，看是否含 ret=101/iRet=101 或 message 含“登录”
        try:
            j = resp.json()
        except Exception:
            return resp.status_code in (401, 403)

        if isinstance(j, dict):
            if j.get("ret") == 101 or j.get("iRet") == 101:
                return True
            msg = str(j.get("sMsg") or j.get("message") or "")
            if "登录" in msg or "未授权" in msg:
                return True

        return resp.status_code in (401, 403)


# =========================
# 快速自测（可直接运行）
# =========================
if __name__ == "__main__":
    cfg = CookieManagerConfig(
        api_key=API_KEY,
        refresh_url=WECHAT_REFRESH_URL,
        token_url=WECHAT_TOKEN_URL,
    )
    mgr = WechatCookieManager(cfg)
    ck = mgr.refresh()
    print("✅ refresh OK, cookie length =", len(ck))
    print("cookie preview:", ck[:120] + ("..." if len(ck) > 120 else ""))
