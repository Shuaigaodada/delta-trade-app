# src/services/request_service.py
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests

from src.config import SEARCH_BASE

API_KEY = ""
FRAMEWORK_TOKEN = ""

FRAMEWORK_TOKEN_PATH = Path("data") / "frameworkToken"
API_KEY_PATH = Path("data") / "API_KEY"


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
# 货币查询（你给的新接口）
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
    # ✅ 关键：默认永远读文件最新 token
    token = (framework_token or read_framework_token() or "").strip()
    if not token:
        return []

    url = f"{SEARCH_BASE}/df/person/money"
    headers = _auth_headers()

    # frameworkToken 是 query array
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
