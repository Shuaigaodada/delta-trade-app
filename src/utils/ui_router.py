# src/utils/ui_router.py
import gradio as gr

def show_pages(*visibles: bool):
    return tuple(gr.update(visible=v) for v in visibles)

def goto_page(index: int, total: int):
    vis = [False] * total
    vis[index] = True
    return show_pages(*vis)
