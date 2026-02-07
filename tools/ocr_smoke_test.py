import os
from paddleocr import PaddleOCR

img_path = r"D:\programing\delta-trade-app\logs\ocr_debug\roi2_bgr_big.png"  # 换成真实路径

print("exists:", os.path.exists(img_path), img_path)

ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False, drop_score=0.2)

res = ocr.ocr(img_path)  # ✅ 直接传路径，最稳
print(res)

# 打印识别文本
texts = []
if res and res[0]:
    for item in res[0]:
        texts.append(item[1][0])
print("texts:", texts)
