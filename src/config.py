import sys
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]  # src 上一级（项目根目录）

BASE_DIR = get_base_dir()

LOG_DIR = str(BASE_DIR / "data" / "logs")
ITEMS_JSON_PATH = str(BASE_DIR / "data" / "items.json")
CSS_PATH = str(BASE_DIR / "static" / "style.css")
OCR_HINT_IMAGE = str(BASE_DIR / "static" / "ocr_hint.png")

SERVER_NAME = "0.0.0.0"
SERVER_PORT = 7860

PAGE_SIZE = 20


SEARCH_BASE = "https://df-api.shallow.ink"
PRICE_URL = "https://comm.ams.game.qq.com/ide/"

# 最新均价接口固定参数
PRICE_PARAMS_BASE = {
    "iChartId": "316969",
    "iSubChartId": "316969",
    "sIdeToken": "NoOapI",
    "method": "dfm/object.price.latest",
    "source": "2",
}