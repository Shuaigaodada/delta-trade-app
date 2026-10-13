# src/services/request_service.py
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests

from src.config import SEARCH_BASE
from src.config import BASE_DIR

API_KEY = ""
FRAMEWORK_TOKEN = ""

DATA_DIR = BASE_DIR / "data"

FRAMEWORK_TOKEN_PATH = DATA_DIR / "frameworkToken"
API_KEY_PATH = DATA_DIR / "API_KEY"
FRAMEWORK_TOKEN_META_PATH = DATA_DIR / "frameworkToken_meta.json"


def _now_ts() -> int:
    return int(time.time())


def load_private_data():
    global API_KEY, FRAMEWORK_TOKEN
    try:
        API_KEY = API_KEY_PATH.read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"加载 API_KEY 失败: {e}")
        raise

    # 兼容：启动时读一次（但真正请求会 read_framework_token()）
    try:
        FRAMEWORK_TOKEN = FRAMEWORK_TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        FRAMEWORK_TOKEN = ""


load_private_data()


def read_framework_token() -> str:
    """
    永远从文件读取最新 frameworkToken（纯文本一行）
    """
    try:
        return FRAMEWORK_TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def write_framework_token(token: str) -> str:
    """
    写入 frameworkToken 到 data/frameworkToken（纯文本一行）
    并更新内存变量（兼容已有逻辑）
    """
    global FRAMEWORK_TOKEN
    t = (token or "").strip()
    FRAMEWORK_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRAMEWORK_TOKEN_PATH.write_text(t, encoding="utf-8")
    FRAMEWORK_TOKEN = t
    return t


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }


# =========================================================
# ✅ frameworkToken 生命周期管理（低频 check + 快过期才 refresh）
# =========================================================
def _meta_load() -> Dict[str, Any]:
    if not FRAMEWORK_TOKEN_META_PATH.exists():
        return {}
    try:
        obj = json.loads(FRAMEWORK_TOKEN_META_PATH.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _meta_save(meta: Dict[str, Any]) -> None:
    FRAMEWORK_TOKEN_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRAMEWORK_TOKEN_META_PATH.write_text(
        json.dumps(meta or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _parse_expire_ts(token_info_json: Dict[str, Any]) -> Optional[int]:
    """
    尽量兼容解析过期时间：
    - 直接给 expire / expireAt / expiresAt / exp：可能是 epoch 秒
    - 给 expiresIn / expires_in：可能是秒数
    """
    if not isinstance(token_info_json, dict):
        return None

    # 可能放在 data 里
    data = token_info_json.get("data")
    if isinstance(data, dict):
        src = data
    else:
        src = token_info_json

    # 1) epoch seconds
    for k in ["expire", "expireAt", "expiresAt", "exp", "expiredAt", "expire_at"]:
        v = src.get(k)
        if v is None:
            continue
        try:
            v_int = int(v)
            # 简单判断：epoch 秒通常 > 1e9
            if v_int > 1_000_000_000:
                return v_int
        except Exception:
            pass

    # 2) expiresIn seconds
    for k in ["expiresIn", "expires_in", "expireIn", "expire_in"]:
        v = src.get(k)
        if v is None:
            continue
        try:
            sec = int(float(v))
            if sec > 0:
                return _now_ts() + sec
        except Exception:
            pass

    return None


def api_wechat_token_info(framework_token: str) -> Dict[str, Any]:
    """
    GET /login/wechat/token?token=frameworkToken
    用于拿到 token 信息（我们只关心过期时间字段）
    """
    token = (framework_token or "").strip()
    if not token:
        return {"success": False, "message": "empty frameworkToken"}

    url = f"{SEARCH_BASE}/login/wechat/token"
    headers = _auth_headers()
    params = {"token": token}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
    except Exception as e:
        return {"success": False, "message": f"request error: {e}"}

    try:
        j = resp.json()
    except Exception:
        return {"success": False, "message": f"non-json: {resp.text[:200]}"}

    # 兼容：有的返回 success，有的返回 code==0
    if j.get("success") is False:
        return j
    if "code" in j and j.get("code") not in (0, "0"):
        return j

    return j


def api_wechat_refresh(framework_token: str) -> Dict[str, Any]:
    """
    GET /login/wechat/refresh?frameworkToken=xxx
    ⚠️ 开销大：只允许在快过期时调用
    """
    token = (framework_token or "").strip()
    if not token:
        return {"success": False, "message": "empty frameworkToken"}

    url = f"{SEARCH_BASE}/login/wechat/refresh"
    headers = _auth_headers()
    params = {"frameworkToken": token}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
    except Exception as e:
        return {"success": False, "message": f"request error: {e}"}

    try:
        j = resp.json()
    except Exception:
        return {"success": False, "message": f"non-json: {resp.text[:200]}"}

    return j


def api_wechat_qr() -> Dict[str, Any]:
    """
    GET /login/wechat/qr
    返回包含 frameworkToken + qr_image
    """
    url = f"{SEARCH_BASE}/login/wechat/qr"
    headers = _auth_headers()

    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        return {"success": False, "message": f"request error: {e}"}

    try:
        j = resp.json()
    except Exception:
        return {"success": False, "message": f"non-json: {resp.text[:200]}"}
    return j


def api_wechat_status(framework_token: str) -> Dict[str, Any]:
    """
    GET /login/wechat/status?frameworkToken=xxx
    你的脚本里是 frameworkToken 参数名；这里按你现有逻辑用 frameworkToken
    """
    token = (framework_token or "").strip()
    if not token:
        return {"success": False, "message": "empty frameworkToken"}

    url = f"{SEARCH_BASE}/login/wechat/status"
    headers = _auth_headers()
    params = {"frameworkToken": token}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
    except Exception as e:
        return {"success": False, "message": f"request error: {e}"}

    try:
        j = resp.json()
    except Exception:
        return {"success": False, "message": f"non-json: {resp.text[:200]}"}

    return j


def _ok_like(j: Dict[str, Any]) -> bool:
    if not isinstance(j, dict):
        return False
    if j.get("success") is True:
        return True
    if "code" in j and j.get("code") in (0, "0"):
        return True
    return False


def get_framework_token_status(
    framework_token: Optional[str] = None,
    cache_ttl_sec: int = 10 * 60,
) -> Dict[str, Any]:
    """
    低开销：优先读 meta 缓存（ttl 内不重复打 /login/wechat/token）
    返回：
      {
        "token": "...",
        "expire_ts": 1770.. or None,
        "seconds_left": ... or None,
        "need_refresh": bool,
        "meta": {...}
      }
    """
    token = (framework_token or read_framework_token() or "").strip()
    if not token:
        return {
            "token": "",
            "expire_ts": None,
            "seconds_left": None,
            "need_refresh": False,
            "meta": {},
            "message": "empty frameworkToken",
        }

    meta = _meta_load()
    meta_token = (meta.get("token") or "").strip()
    checked_at = int(meta.get("checked_at") or 0)
    expire_ts = meta.get("expire_ts")

    # 只在：同一个 token 且 ttl 未过期时使用缓存
    if meta_token == token and checked_at and (_now_ts() - checked_at) <= cache_ttl_sec:
        pass
    else:
        info = api_wechat_token_info(token)
        expire_ts2 = _parse_expire_ts(info)

        meta = {
            "token": token,
            "checked_at": _now_ts(),
            "expire_ts": expire_ts2,
            "raw": info,
        }
        _meta_save(meta)
        expire_ts = expire_ts2

    seconds_left = None
    if isinstance(expire_ts, int) and expire_ts > 0:
        seconds_left = int(expire_ts - _now_ts())

    return {
        "token": token,
        "expire_ts": expire_ts if isinstance(expire_ts, int) else None,
        "seconds_left": seconds_left,
        "need_refresh": False,  # 这里不做判断
        "meta": meta,
    }


def ensure_framework_token_valid(
    framework_token: Optional[str] = None,
    refresh_interval_sec: int = 90 * 60,  # ✅ 1.5 小时
    cache_ttl_sec: int = 10 * 60,
) -> Dict[str, Any]:
    """
    强制按时间间隔 refresh（不依赖 expire_ts）
    每 refresh_interval_sec 才允许刷新一次
    """

    token = (framework_token or read_framework_token() or "").strip()
    if not token:
        return {
            "ok": False,
            "did_refresh": False,
            "need_reauth": True,
            "seconds_left": None,
            "expire_ts": None,
            "message": "frameworkToken 为空",
        }

    meta = _meta_load()
    last_refresh = int(meta.get("refreshed_at") or 0)

    now = _now_ts()
    delta = now - last_refresh

    # 🔹 未到刷新间隔 → 不 refresh
    if last_refresh and delta < refresh_interval_sec:
        left = refresh_interval_sec - delta
        return {
            "ok": True,
            "did_refresh": False,
            "need_reauth": False,
            "seconds_left": None,
            "expire_ts": None,
            "message": f"未到定时刷新间隔（剩余 {left}s）",
        }

    # 🔥 到时间 → 强制 refresh
    r = api_wechat_refresh(token)

    if not _ok_like(r):
        return {
            "ok": False,
            "did_refresh": True,
            "need_reauth": True,
            "seconds_left": None,
            "expire_ts": None,
            "message": f"refresh 失败：{r.get('message') or r.get('msg') or r}",
            "raw": r,
        }

    # 刷新成功 → 更新 meta
    meta = {
        "token": token,
        "checked_at": now,
        "expire_ts": None,
        "raw": {},
        "refreshed_at": now,
        "refresh_raw": r,
    }
    _meta_save(meta)

    return {
        "ok": True,
        "did_refresh": True,
        "need_reauth": False,
        "seconds_left": None,
        "expire_ts": None,
        "message": "定时 refresh 成功",
    }



# =========================
# 物品搜索（不需要 cookie）
# =========================
def search_item(keyword: str) -> list[dict]:
    url = f"{SEARCH_BASE}/df/object/search"
    headers = _auth_headers()
    params = {"name": keyword}

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    if resp.status_code != 200:
        print("搜索接口失败:", resp.status_code)
        print(resp.text)
        return []

    data = resp.json()
    if not data.get("success"):
        print("搜索失败:", data)
        return []

    return data["data"]["keywords"]


# =========================
# 官方最新均价（不需要 cookie）
# =========================
def get_latest_price(object_ids: list[int]) -> dict:
    url = f"{SEARCH_BASE}/df/object/price/latest"
    headers = _auth_headers()
    params = {"id": object_ids}

    resp = requests.get(url, headers=headers, params=params, timeout=10)
    if resp.status_code != 200:
        print("官方最新均价接口请求失败:", resp.status_code)
        print(resp.text)
        return {}

    data = resp.json()
    if not data.get("success"):
        print("官方最新均价接口失败:", data.get("message"))
        return {}

    prices = data["data"]["prices"]
    price_map = {}
    for item in prices:
        oid = str(item["objectID"])
        price_map[oid] = {"avgPrice": item["avgPrice"]}
    return price_map


# =========================
# 货币查询（依赖 frameworkToken）
# GET /df/person/money
# =========================
def get_person_money(
    framework_token: Optional[str] = None,
    item: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    返回 data 数组，如：
      [{"item":"17020000010","name":"哈夫币","totalMoney":"5915274"}, ...]
    失败返回 []
    """
    # ✅ 默认永远读文件最新 token
    token = (framework_token or read_framework_token() or "").strip()
    if not token:
        return []

    url = f"{SEARCH_BASE}/df/person/money"
    headers = _auth_headers()

    params: Dict[str, Any] = {"frameworkToken": [token]}
    if item:
        params["item"] = item

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
    except Exception as e:
        print("货币查询接口请求异常:", e)
        return []

    if resp.status_code != 200:
        print("货币查询接口失败:", resp.status_code)
        print(resp.text)
        return []

    try:
        data = resp.json()
    except Exception:
        print("货币查询接口返回非 JSON:", resp.text[:200])
        return []

    if not data.get("success"):
        print("货币查询接口 success=false:", data.get("message"))
        return []

    arr = data.get("data") or []
    if not isinstance(arr, list):
        return []
    return arr
