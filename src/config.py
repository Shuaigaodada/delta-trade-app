LOG_DIR = "data/logs"
ITEMS_JSON_PATH = "data/items.json"
CSS_PATH = "static/style.css"

SERVER_NAME = "0.0.0.0"
SERVER_PORT = 7860

PAGE_SIZE = 20

# OCR 失败提示用的示例图（你可以用 tools 脚本生成）
OCR_HINT_IMAGE = "static/ocr_hint.png"


SEARCH_BASE = "https://df-api-eo.shallow.ink"
PRICE_URL = "https://comm.ams.game.qq.com/ide/"

# 最新均价接口固定参数
PRICE_PARAMS_BASE = {
    "iChartId": "316969",
    "iSubChartId": "316969",
    "sIdeToken": "NoOapI",
    "method": "dfm/object.price.latest",
    "source": "2",
}