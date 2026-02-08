import requests
import json
from typing import Optional, Dict, Any, List

from src.config import SEARCH_BASE

API_KEY = ""
FRAMEWORK_TOKEN = ""


def load_private_data():
    global API_KEY, FRAMEWORK_TOKEN
    try:
        with open("data/API_KEY", "r", encoding="utf-8") as f:
            API_KEY = f.read().strip()
    except Exception as e:
        print(f"加载 API_KEY 失败: {e}")
        raise

    # frameworkToken：建议你单独放一个文件 data/frameworkToken
    try:
        with open("data/frameworkToken", "r", encoding="utf-8") as f:
            FRAMEWORK_TOKEN = f.read().strip()
    except Exception:
        FRAMEWORK_TOKEN = ""


load_private_data()


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
    token = (framework_token or FRAMEWORK_TOKEN or "").strip()
    if not token:
        # 没 token 直接返回空，不抛异常
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
