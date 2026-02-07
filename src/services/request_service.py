import requests
import re
import json

from src.config import SEARCH_BASE, PRICE_PARAMS_BASE, PRICE_URL



COOKIE = ""
API_KEY = ""
ContentType = "application/x-www-form-urlencoded;"


def load_private_data():
    """
    load_private_data 的 Docstring
    """
    
    global COOKIE, API_KEY
    try:
        with open("data/cookies", "r", encoding="utf-8") as f:
            COOKIE = f.read().strip()
        with open("data/API_KEY", "r", encoding="utf-8") as f:
            API_KEY = f.read().strip()
    except Exception as e:
        print(f"加载私密数据失败: {e}")
        raise
            

load_private_data()    

def extract_df_cookie(raw_cookie: str) -> str:
    """
    extract_df_cookie 的 Docstring
    
    :param raw_cookie: 原始 cookie 字符串，包含多个键值对，例如 "openid=...; acctype=qc; appid=...; access_token=..."
    :type raw_cookie: str
    :return: 提取并重组后的 cookie 字符串，格式为 "openid=...; acctype=...; appid=...; access_token=..."
    :rtype: str
    """
    def get_value(key: str) -> str:
        m = re.search(rf"(?:^|;\s*){re.escape(key)}=([^;]*)", raw_cookie)
        return m.group(1).strip() if m else ""

    _openid = get_value("openid")
    acctype = get_value("acctype")
    appid = get_value("appid")
    access_token = get_value("access_token")

    if not _openid or not acctype or not appid or not access_token:
        raise ValueError("cookie缺少必要字段：openid/acctype/appid/access_token")

    cookie = f"openid={_openid}; acctype={acctype}; appid={appid}; access_token={access_token}"
    return cookie

def query_currency_total_money(cookie: str, item: str) -> int:
    """
    query_currency_total_money 的 Docstring
    
    :param cookie: 已提取并重组的 cookie 字符串，格式为 "openid=...; acctype=...; appid=...; access_token=..."
    :type cookie: str
    :param item: 货币类型，17020000010 哈夫币，17888808889 三角券，17888808888 三角币
    :type item: str
    :return: 该货币的总量，单位为 k（整数）
    :rtype: int
    """
    params = {
        "iChartId": "319386",
        "iSubChartId": "319386",
        "sIdeToken": "zMemOt",
        "type": "3",
        "item": item,
    }
    
    headers = {
        "Content-Type": ContentType,
        "Cookie": cookie,
    }

    try:
        r = requests.post("https://comm.ams.game.qq.com/ide/", params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"请求失败: {e}")

    if int(data.get("ret", -1)) != 0:
        raise RuntimeError(f"请求失败: ret={data.get('ret')} msg={data.get('sMsg')}")

    jdata = data.get("jData", {})
    arr = jdata.get("data", [])
    if not arr:
        return 0
    return int(arr[0].get("totalMoney", "0"))

def current_account_assets(cookie: str) -> dict:
    """
    current_account_assets 的 Docstring
    
    :param cookie: 已提取并重组的 cookie 字符串，格式为 "openid=...; acctype=...; appid=...; access_token=..."
    :type cookie: str
    :return: 当前账号的纯币总量，单位为 k（整数）
    :rtype: dict
    """
    hav = query_currency_total_money(cookie, "17020000010")
    ticket = query_currency_total_money(cookie, "17888808889")
    coin = query_currency_total_money(cookie, "17888808888")
    return {"hav": hav, "ticket": ticket, "coin": coin}
    
def search_item(keyword: str) -> list[dict]:
    
    
    url = f"{SEARCH_BASE}/df/object/search"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "User-Agent": "Mozilla/5.0"
    }
    
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

def get_latest_price(object_ids: list[int]):
    headers = {
        "content-type": "application/x-www-form-urlencoded;",
        "cookie": COOKIE,
        "User-Agent": "Mozilla/5.0"
    }

    params = PRICE_PARAMS_BASE.copy()
    params["param"] = json.dumps({"objectID": object_ids}, ensure_ascii=False)

    resp = requests.post(PRICE_URL, params=params, headers=headers, timeout=10)

    if resp.status_code != 200:
        print("最新均价接口请求失败:", resp.status_code)
        print(resp.text)
        return {}

    data = resp.json()

    # 检查是否登录失效
    if data.get("ret") == 101 or data.get("iRet") == 101:
        print("Cookie失效或未登录:", data.get("sMsg"))
        return {}

    try:
        return data["jData"]["data"]["data"]["dataMap"]
    except Exception:
        print("解析 dataMap 失败，返回内容如下：")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return {}


if __name__ == "__main__":
    # 示例用法
    # try:
    #     cookie = extract_df_cookie(COOKIE)
    #     print("提取后的 cookie:", cookie)
    #     assets = current_account_assets(cookie)
    #     print("当前账号资产:", assets)
    # except Exception as e:
    #     print(f"发生错误: {e}")
    
    keyword = input("请输入物品关键词：").strip()

    # 1. 搜索物品
    results = search_item(keyword)
    print(results)
    exit()
    
    if not results:
        print("没有搜索到任何物品")
        exit()

    print("\n====== 搜索结果 ======")
    for i, item in enumerate(results, start=1):
        print(f"[{i}] {item['objectName']} | objectID={item['objectID']} | avgPrice={item['avgPrice']}")

    
    # 2. 让用户选择
    choice = input("\n请输入要查询最新均价的序号（默认1）：").strip()
    if choice == "":
        choice = "1"

    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(results):
        print("输入无效，退出")
        exit()

    selected_item = results[int(choice) - 1]
    object_id = selected_item["objectID"]

    print("\n====== 你选择的物品 ======")
    print(f"物品名: {selected_item['objectName']}")
    print(f"objectID: {object_id}")
    print(f"搜索接口 avgPrice: {selected_item['avgPrice']}")

    # 3. 查询最新均价
    latest_price_map = get_latest_price([object_id])

    if not latest_price_map:
        print("最新均价接口没有返回数据")
        exit()

    oid_str = str(object_id)

    if oid_str in latest_price_map:
        latest_avg_price = latest_price_map[oid_str]["avgPrice"]
        print("\n====== 最新均价接口结果 ======")
        print(f"最新 avgPrice: {latest_avg_price}")
    else:
        print("最新均价接口没有该物品的数据")
