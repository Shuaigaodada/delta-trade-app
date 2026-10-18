import os
from pathlib import Path

 
# 关闭 paddle 编译扩展（核心修复）
os.environ["PADDLE_DISABLE_CPP_EXTENSION"] = "1"

# 你之前那个也一起加
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# 推荐一起加（你项目里本来就有）
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_use_pir_api"] = "0"
os.environ["FLAGS_new_executor"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"

import gradio as gr
from src.ui.page import build_app
from src.config import BASE_DIR, CSS_PATH, SERVER_NAME, SERVER_PORT


css = open(CSS_PATH, encoding="utf-8").read()

demo = build_app(css=css)

# ✅ Windows 下务必用绝对路径
STATIC_DIR = (BASE_DIR / "static").resolve()

demo.launch(
    server_name=SERVER_NAME,
    server_port=SERVER_PORT,
    css=css,
    allowed_paths=[str(STATIC_DIR)],
)
