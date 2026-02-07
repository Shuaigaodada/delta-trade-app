import json
from src.config import ITEMS_JSON_PATH

FAKE_PRICES = {
    "留声机": 12325,
    "机甲": 8650,
    "红卡": 22000,
    "高级医疗包": 980,
    "战术电池": 420,
    "稀有零件": 1550,
    "军用硬盘": 7600,
    "实验室钥匙卡": 31000,
}

def load_items():
    with open(ITEMS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def build_gallery(items):
    gallery = []
    for item in items:
        name = item["name"]
        price = FAKE_PRICES.get(name, 999)
        caption = f"{name}\n{price}k"
        gallery.append((item["img"], caption))
    return gallery

def filter_items(all_items, keyword: str):
    keyword = (keyword or "").strip()
    if keyword == "":
        filtered = all_items
    else:
        filtered = [x for x in all_items if keyword in x["name"]]
    names = [x["name"] for x in filtered]
    new_value = names[0] if names else None
    return filtered, names, new_value

def parse_gallery_select(evt_value):
    if isinstance(evt_value, dict) and "caption" in evt_value:
        cap = evt_value["caption"]
    elif isinstance(evt_value, (tuple, list)) and len(evt_value) >= 2:
        cap = evt_value[1]
    else:
        cap = evt_value

    if isinstance(cap, str):
        return cap.splitlines()[0].strip()
    return cap
