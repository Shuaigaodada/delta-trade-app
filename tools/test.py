import requests
import json

# ========== 配置区 ==========
SEARCH_BASE = "https://df-api-eo.shallow.ink"
SEARCH_API_KEY = "sk-UjhpQv7IuyiYOf91qHLaout1O3okryMs"  # TODO: 替换成你新的 key（sk-xxxx）

PRICE_URL = "https://comm.ams.game.qq.com/ide/"

# TODO: 替换成你自己的 cookie（必须能登录）
COOKIE = "openid=oDj4vwr8K56r2ZFrC6aRDsqSHLQ4; acctype=wx; appid=wxfa0c35392d06b82f; access_token=100_kev4PNlamH2VYHZj4lTGBUwBw6evtu-HPRCgt3NVdbyN_59CZya5VBzn1FJ1b_Esk5dJK8GZ5lIVxa9GhDCnmhRMQvdxts0EWTod7cBljUQ"

# 最新均价接口固定参数
PRICE_PARAMS_BASE = {
    "iChartId": "316969",
    "iSubChartId": "316969",
    "sIdeToken": "NoOapI",
    "method": "dfm/object.price.latest",
    "source": "2",
}


# ========== 物品搜索接口 ==========
def search_item(keyword: str):
    url = f"{SEARCH_BASE}/df/object/search"

    headers = {
        "Authorization": f"Bearer {SEARCH_API_KEY}",
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


# ========== 最新均价接口 ==========
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


# ========== 主程序 ==========
if __name__ == "__main__":
    keyword = input("请输入物品关键词：").strip()

    # 1. 搜索物品
    results = search_item(keyword)

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
