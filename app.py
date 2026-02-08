import os
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_use_pir_api"] = "0"
os.environ["FLAGS_new_executor"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"


import gradio as gr
from src.ui.page import build_app
from src.config import CSS_PATH, SERVER_NAME, SERVER_PORT

css = open(CSS_PATH, "r", encoding="utf-8").read()

demo = build_app(css=css)
demo.launch(server_name=SERVER_NAME, server_port=SERVER_PORT, css=css)
