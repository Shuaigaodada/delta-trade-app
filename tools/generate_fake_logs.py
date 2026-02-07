import os
from datetime import datetime, timedelta
import random

LOG_DIR = "logs"

def format_k(n: int) -> str:
    return f"{n}k"

def make_one_log(ts: datetime, idx: int) -> str:
    ran = random.randint(3000, 12000)         # 已跑纯币
    reserve_value = random.randint(5000, 40000)
    before_total = random.randint(1000, 8000)
    after_total = before_total + random.randint(5000, 25000)
    prepay = round(random.uniform(10, 200), 2)

    reserve_items = [
        ("留声机", random.randint(0, 2)),
        ("机甲", random.randint(0, 3)),
        ("红卡", random.randint(0, 6)),
        ("军用硬盘", random.randint(0, 2)),
        ("实验室钥匙卡", random.randint(0, 1)),
    ]
    reserve_items = [(n, c) for n, c in reserve_items if c > 0]
    if not reserve_items:
        reserve_items = [("留声机", 1)]

    reserve_text = "，".join([f"{n}x{c}" for n, c in reserve_items])

    return (
        "注意，以下是最终提交的日志，请阅读后确保没有任何问题。\n"
        f"知神在{ts.strftime('%Y-%m-%d %H:%M:%S')} 提交了最新的日志\n"
        f"已跑纯币为{format_k(ran)}\n"
        f"预留物品为：{reserve_text}\n"
        f"预留物品总价值为：{format_k(reserve_value)}\n"
        f"未结算前总纯：{format_k(before_total)}\n"
        f"结算后总纯：{format_k(after_total)}（膜拜知神）\n"
        f"消耗预付款为：{prepay}元\n"
        f"(日志编号: {idx})\n"
    )

def main(count: int = 20, minutes_step: int = 3):
    os.makedirs(LOG_DIR, exist_ok=True)

    now = datetime.now()
    # 生成最近一段时间的日志：每条间隔 minutes_step 分钟
    for i in range(count):
        ts = now - timedelta(minutes=i * minutes_step)
        filename = ts.strftime("%Y-%m-%d_%H-%M-%S") + ".txt"
        path = os.path.join(LOG_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(make_one_log(ts, i + 1))

    print(f"✅ 已生成 {count} 条日志到 {LOG_DIR}/ 目录下")

if __name__ == "__main__":
    # 你可以改这里的数量/间隔
    main(count=30, minutes_step=2)
