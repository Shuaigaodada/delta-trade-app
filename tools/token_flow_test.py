# tools/token_flow_test.py
import sys
import time
import json
from pathlib import Path

# 让直接运行/ -m 都能找到 src
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services import request_service


def pretty(x):
    try:
        return json.dumps(x, ensure_ascii=False, indent=2)
    except Exception:
        return repr(x)


def _ok_like(j: dict) -> bool:
    if not isinstance(j, dict):
        return False
    if j.get("success") is True:
        return True
    if "code" in j and j.get("code") in (0, "0"):
        return True
    return False


def _status_is_confirmed(j: dict) -> bool:
    """
    尽量兼容不同后端字段：
    - success=True / code==0 只是“接口成功”，不代表“已确认”
    - 需要判断 data 内是否进入已登录/已确认态
    """
    if not isinstance(j, dict):
        return False

    # 有些后端直接平铺返回状态字段
    data = j.get("data") if isinstance(j.get("data"), dict) else j

    # 常见布尔字段
    for k in ("confirmed", "confirm", "isConfirm", "isConfirmed",
              "logged", "isLogin", "login", "logined",
              "authed", "authorized", "isAuth"):
        v = data.get(k)
        if v is True:
            return True
        if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes", "ok"):
            return True

    # 常见状态字段（字符串/数字）
    status_val = data.get("status") or data.get("state") or data.get("scanStatus") or data.get("qrStatus")
    if status_val is not None:
        s = str(status_val).strip().lower()
        # 你们可能返回：done/confirmed/ok/success/logged/login/authorized
        if s in ("done", "confirmed", "confirm", "ok", "success", "logged", "login", "authorized", "authed"):
            return True
        # 有些返回数字：2/3 表示已确认（这里做宽松兼容）
        if s in ("2", "3", "200"):
            return True

    # 有些返回 message 里直接写了已登录/成功
    msg = str(j.get("msg") or j.get("message") or "")
    if any(x in msg for x in ("已登录", "登录成功", "已确认", "授权成功")):
        return True

    return False


def wait_for_scan(framework_token: str, timeout_sec: int = 120, interval_sec: float = 2.0):
    """
    ✅ 使用 request_service.api_wechat_status() 轮询，不自己拼 requests
    """
    t0 = time.time()
    last = None
    while True:
        j = request_service.api_wechat_status(framework_token)
        last = j

        # 接口不成功就继续等（避免中途抖动）
        if _ok_like(j):
            if _status_is_confirmed(j):
                return True, j

        if time.time() - t0 >= timeout_sec:
            return False, last

        time.sleep(interval_sec)


def main():
    # 0) 扫码前先查一次货币（大概率 401 / 空，正常）
    print("===== 0) 扫码前：查一次货币（可能失败/空） =====")
    m0 = request_service.get_person_money(item="17020000010")
    print(pretty(m0))

    # 1) 生成二维码（使用 request_service.api_wechat_qr）
    print("\n===== 1) 获取二维码 =====")
    qr = request_service.api_wechat_qr()
    print(pretty(qr))

    if not _ok_like(qr):
        raise SystemExit("❌ 获取二维码失败")

    # ✅ 兼容：data 包裹 or 平铺字段
    data = qr.get("data") if isinstance(qr.get("data"), dict) else qr

    ft = (data.get("frameworkToken") or data.get("framework_token") or data.get("token") or "").strip()
    qr_img = data.get("qr_image") or data.get("qrImage") or data.get("qr")

    if not ft:
        raise SystemExit("❌ 返回里没有 frameworkToken（把 /login/wechat/qr 返回 JSON 发我，我给你精确适配字段）")

    if qr_img:
        print(f"\n🔗 扫码链接（浏览器打开）：{qr_img}")

    # 写入 data/frameworkToken，后续默认读这个文件
    request_service.write_framework_token(ft)
    print(f"\n✅ 已写入 frameworkToken 到 data/frameworkToken：{ft[:8]}...")

    # 2) 轮询扫码（使用 request_service.api_wechat_status）
    print("\n===== 2) 等待用户扫码确认（轮询 /login/wechat/status） =====")
    ok, st = wait_for_scan(ft, timeout_sec=120, interval_sec=2.0)
    print(pretty(st))
    if not ok:
        raise SystemExit("❌ 扫码等待超时/未确认（如果你能贴一份“未扫码时 status 返回”和“扫码成功后 status 返回”，我可以把判断写成 100% 精准）")

    # 3) 检查 token 状态（强制查一次，跳过 meta ttl）
    print("\n===== 3) 检查 frameworkToken 状态（强制查询 token info） =====")
    s1 = request_service.get_framework_token_status(cache_ttl_sec=0)
    print(pretty(s1))

    # 4) 刷新 token（演示：强制触发 refresh；线上改回 6h 阈值）
    print("\n===== 4) 刷新 frameworkToken（演示：强制触发 refresh） =====")
    r = request_service.ensure_framework_token_valid(
        refresh_threshold_sec=10**9,  # 仅测试：强制刷新
        cache_ttl_sec=0,
    )
    print(pretty(r))

    # 5) 再检查一次
    print("\n===== 5) refresh 后再查一次 token 状态 =====")
    s2 = request_service.get_framework_token_status(cache_ttl_sec=0)
    print(pretty(s2))

    # 6) 测试：查一次货币
    print("\n===== 6) 测试：查询一次货币（哈夫币） =====")
    m1 = request_service.get_person_money(item="17020000010")
    print(pretty(m1))

    # 7) 再查一次货币
    print("\n===== 7) 再查询一次货币（哈夫币） =====")
    m2 = request_service.get_person_money(item="17020000010")
    print(pretty(m2))

    print("\n✅ 流程完成")


if __name__ == "__main__":
    main()