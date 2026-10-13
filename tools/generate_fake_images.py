import os
from PIL import Image, ImageDraw, ImageFont

ITEMS = ["留声机", "机甲", "红卡", "高级医疗包", "战术电池", "稀有零件", "军用硬盘", "实验室钥匙卡"]

def get_text_size(draw, text, font):
    # Pillow 新版本推荐 multiline_textbbox
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=6, align="center")
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return w, h

def main():
    out_dir = os.path.join("static", "items")
    os.makedirs(out_dir, exist_ok=True)

    # 尝试用微软雅黑（支持中文）
    try:
        font = ImageFont.truetype("C:\\Windows\\Fonts\\msyh.ttc", 28)
    except Exception:
        font = ImageFont.load_default()

    for name in ITEMS:
        img = Image.new("RGB", (160, 160), (245, 245, 245))
        draw = ImageDraw.Draw(img)

        # 边框
        draw.rectangle([6, 6, 154, 154], outline=(200, 200, 200), width=3)

        # 文本换行
        text = name
        if len(text) > 4:
            text = text[:4] + "\n" + text[4:]

        w, h = get_text_size(draw, text, font)

        x = (160 - w) / 2
        y = (160 - h) / 2

        draw.multiline_text(
            (x, y),
            text,
            fill=(40, 40, 40),
            font=font,
            align="center",
            spacing=6
        )

        path = os.path.join(out_dir, f"{name}.png")
        img.save(path)

    print("✅ 已生成假图片到 static/items/")

if __name__ == "__main__":
    main()
