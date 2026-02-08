FRAMEWORK = "7f48071b-45b2-49ac-94b3-b628849edcd6"
import requests

res = requests.get(f"https://login/wechat/refresh?frameworkToken={FRAMEWORK}")

if res.status_code != 200:
    raise RuntimeError(f"请求失败，状态码：{res.status_code}")
print("响应内容：", res.text)
