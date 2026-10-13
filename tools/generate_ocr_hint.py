from PIL import Image, ImageDraw, ImageFont
import os

OUT_PATH = "static/ocr_hint.png"

def main():
    os.makedirs("static", exist_ok=True)
    w, h = 900, 380
    img = Image.new("RGB", (w, h), (245, 245, 245))
    draw = ImageDraw.Draw(img)

    # 主框
    draw.rectangle([20, 20, w-20, h-20], outline=(80, 80, 80), width=3)

    # 右上角 ROI 框
    roi = [w-320, 35, w-35, 140]
    draw.rectangle(roi, outline=(255, 60, 60), width=5)

    # 箭头
    draw.line([w-360, 200, roi[0]+30, roi[1]+30], fill=(255, 60, 60), width=6)

    # 文本
    text1 = "示例：把右上角“纯币 xxxxxk”区域放大/裁剪后再截图"
    text2 = "要求：数字清晰、不糊、不要被图标遮挡"
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()

    draw.text((35, 240), text1, fill=(30, 30, 30), font=font)
    draw.text((35, 285), text2, fill=(30, 30, 30), font=font)

    # “xxxxxk”示意
    draw.text((roi[0]+20, roi[1]+25), "12345k", fill=(0, 0, 0), font=font)

    img.save(OUT_PATH)
    print(f"✅ 已生成 {OUT_PATH}")

if __name__ == "__main__":
    main()
