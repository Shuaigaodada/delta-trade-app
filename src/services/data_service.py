import json
import os

def load_finance_data() -> dict:
    """加载财务数据"""
    finance_file = "data/finance.json"
    if not os.path.exists(finance_file):
        # 如果文件不存在，返回默认数据
        return {
            "proportion": 22,
            "prepayment": 0,
            "current_account_balance": 0,
            "today_income": 0,
            "total_income": 0
        }
    with open(finance_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data