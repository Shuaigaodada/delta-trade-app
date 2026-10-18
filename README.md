# delta-trade-app / 三角洲个人跑刀计算

三角洲行动「跑刀」收益结算 Web 工具：上传上号/下号纯币截图自动 OCR 识别，查询物品交易行均价，计算本次纯币变化、预留物品价值与折算人民币，并按预付款结算、归档日志。

## 简介

这是一个基于 Gradio 的本机网页应用，用来替代手工记账：把上号与下号时的「纯币」截图传给页面，工具用 PaddleOCR 识别右上角数字，再结合交易行均价计算本次收益，最后生成本次结算日志并写入 `data/logs/`、更新预付款余额。

主要能力：

- **结算**：上传上号/下号资产截图 → OCR 识别纯币 → 填写预留物品 → 生成结算文本 → 确认后落盘。
- **物品均价**：搜索道具并获取最新均价，用于计算预留物品价值；也支持手工修改价格。
- **预留物品管理**：按「物品名 x 数量」维护预留物品清单，价值并入本次变化。
- **首页统计**：显示当前预付款、当前账号哈夫币/三角券/三角币、今日已跑金额、累计金额，并列出最近日志（可翻页查看）。
- **管理员面板**：设置预付款余额、写入/读取 `frameworkToken`、扫码获取新的 `frameworkToken`。
- **日志详情**：查看某次结算的文本、上号/下号截图与备注。

## 目录结构

```
delta-trade-app/
├─ app.py                       # 启动入口：设置 Paddle/FLAGS 环境变量后启动 Gradio（0.0.0.0:7860）
├─ src/
│  ├─ config.py                 # 路径、端口、分页大小、df-api / 腾讯 ide 接口地址与固定参数
│  ├─ services/
│  │  ├─ ocr_service.py         # PaddleOCR PP-OCRv3 识别纯币与物品文本
│  │  ├─ request_service.py     # 读取 data/API_KEY、data/frameworkToken，请求搜索/均价/账号资产接口
│  │  ├─ logs_service.py        # 结算日志写入、列表、分页、统计
│  │  └─ finance_service.py     # 预付款余额与变动流水（data/finance.json）
│  ├─ ui/
│  │  ├─ page.py                # Gradio 页面装配与全部回调（OCR 预览、提交、管理员、轮询）
│  │  └─ pages/                 # 首页、结算、物品选择、确认、日志详情、更多日志、预留物品管理
│  └─ utils/                    # 表格、金额格式化、页面切换小工具
├─ static/                      # style.css、OCR 示例图 ocr_hint.png、彩蛋音频 egg_audio/
├─ scripts/
│  ├─ start-prepared-env.ps1    # 校验 .venv 依赖后启动（推荐入口）
│  └─ check-environment.py      # 校验 .venv 路径与 requirements.txt 钉版本
├─ tools/                       # 登录/token/OCR 冒烟测试等调试脚本
├─ data/                        # 运行时私有数据（不入库）：API_KEY、frameworkToken、finance.json、logs/
├─ requirements.txt             # 钉版本依赖（UTF-16 编码）
├─ app.spec / delta-trade-app.spec  # PyInstaller 打包配置
└─ LICENSE
```

## 环境要求

- Windows 10/11 + Python 3.10（仓库内 `.venv` 由 Python 3.10.3 创建）。
- 虚拟环境必须位于项目根目录且名为 `.venv`：`scripts/check-environment.py` 会校验 `sys.prefix` 是否等于 `<项目根>/.venv`，否则拒绝启动。
- 依赖按 `requirements.txt` 钉死版本安装（含 `gradio 6.5.1`、`paddleocr 2.7.3`、`paddlepaddle 2.6.2`、`opencv-python`、`pandas` 等）。
- 需要联网访问 df-api 与游戏官方接口；首次使用 PaddleOCR 会下载 PP-OCRv3 模型，请预留磁盘空间。

## 启动方式（Windows PowerShell）

首次准备环境：

```powershell
cd E:\Projects\delta-trade-app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动（推荐，先校验钉版本依赖，再运行 `app.py`）：

```powershell
cd E:\Projects\delta-trade-app
.\scripts\start-prepared-env.ps1
```

只校验环境、不启动：

```powershell
.\scripts\start-prepared-env.ps1 -CheckEnvironmentOnly
```

手动启动：

```powershell
.\.venv\Scripts\python.exe -B .\app.py
```

启动后浏览器访问 <http://127.0.0.1:7860>。`app.py` 里写的是 `server_name="0.0.0.0"`、`server_port=7860`，因此同一局域网内也可以用本机 IP 访问；请只在可信网络中使用。

## 使用方法

1. **首次准备私有文件**（`data/` 不入库，需要自建）：
   - `data/API_KEY`：纯文本一行 API Key。`src/services/request_service.py` 启动时读取，缺失会直接报错退出，必须先写好。
   - `data/frameworkToken`：纯文本一行 token，可先留空，之后在管理员面板里保存或用扫码流程获取。
   - `data/finance.json`、`data/logs/` 会自动创建。
2. **结算流程**：首页点「【结算】」→ 分别上传上号/下号时资产截图（只截纯币数字区域更准）→ 核对 OCR 识别结果 → 点「管理预留物品」维护清单 → 「【提交】」查看结算文本 → 在确认页填写可选备注 → 「【确认】」写入日志并扣减预付款。
3. **结算规则**（见 `src/ui/page.py` 的提交逻辑）：本次变化 =（下号纯币 − 上号纯币）+ 预留物品价值；按 10 000 纯币 = 1 万、20 万纯币 = 1 元折算；结算金额 = 当前预付款 − 本次折合，并写回预付款余额（允许为负）。计算口径如需调整请改代码。
4. **管理员**：点右下角「管理员」，登录后可设置预付款余额、保存 `frameworkToken`、生成二维码链接并轮询扫码状态，把新 token 保存为当前值。管理员账号密码硬编码在 `src/ui/page.py` 的 `ADMIN_USER` / `ADMIN_PASS`，公开部署前请修改。
5. **日志**：首页表格显示最近 20 条结算记录，点击行查看详情，点「刷新」「【查询更多】」翻页。日志目录形如 `data/logs/<YY-MM-DD_HH-MM-SS>/`，内含 `log.txt` 与上号/下号截图。

## 已知限制

- 单机单用户工具：除硬编码的管理员登录外没有账号体系与权限隔离，不适合多人或公网部署。
- 结算取「今天」时区为 `America/Chicago`（`src/ui/page.py` 的 `TZ`），与国内自然日不一致；跨天统计按该时区切换。
- OCR 依赖截图中纯币数字清晰可见；截图过糊、被图标遮挡或缩放不当会识别失败，需要用 `static/ocr_hint.png` 示例的裁剪方式重拍。
- 交易行均价来自第三方/官方接口（`src/config.py` 的 `SEARCH_BASE`、`PRICE_URL` 及固定参数），接口变更、限流或 token 过期都会导致搜索/均价失败；`frameworkToken` 过期需重新扫码获取。
- `data/API_KEY`、`data/frameworkToken`、`data/finance.json`、`data/logs/` 均为本地私有数据，已被 `.gitignore` 排除，不会随仓库分发。
- PyInstaller 打包（`app.spec` / `delta-trade-app.spec`）未在本 README 中验证；打包后 `data/`、`static/` 需随程序目录一起分发。
- `tools/` 下是开发调试脚本，不属于运行时依赖，运行前需自行确认其参数与副作用。

## 许可

见 [LICENSE](LICENSE)。
