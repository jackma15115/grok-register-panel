<div align="center">

# Grok Register + Live Panel

Based on [AaronL725/grok-register](https://github.com/AaronL725/grok-register) (MIT).

批量注册 Grok 账号（Camoufox）+ Web 监控面板  
启停 / 并发 / ASN 黑名单 / 1h·3h·12h 成功率 / **Token 鉴权**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)
![Stars](https://img.shields.io/github/stars/lij768423-svg/grok-register-panel?style=flat)

**仓库：** https://github.com/lij768423-svg/grok-register-panel

</div>

---

> **声明：** 仅供自动化流程研究、自有环境联调与个人学习。请遵守 xAI / 邮箱 / 代理服务商条款与当地法律，勿用于未授权批量滥用。

## 功能一览

| 能力 | 说明 |
|------|------|
| 注册全链路 | 邮箱 OTP → 资料页 → Turnstile → SSO → Device / OAuth → 写入 CPA / Grok2API |
| 多邮箱后端 | Cloudflare Worker 邮、DuckMail、YYDS、MailNest、CloudMail 等 |
| 反检测浏览器 | [Camoufox](https://camoufox.com/)（Gecko 层指纹） |
| 出口预检 | 启动前解析出口 IP / ASN，命中黑名单直接换口 |
| 风控早停 | `botFlagSource=1` + `policy=deny` 时跳过后续 OAuth，避免无效重试 |
| 编排器 | 多轮 batch、风控满 N 暂停、ASN 自动扩黑；规则写入 JSON 状态，不修改源码 |
| **Live 面板** | 启停、并发、再跑 N、黑名单、时段成功率和账号补录；操作 API 需 `MONITOR_TOKEN` |
| 导入账号登录 | 导入 `email + password`，浏览器登录 xAI 后提取 SSO，并可继续写入 CPA / Grok2API |
| 外部代理池 | 面板单条/批量导入、去重、探活、启停、删除；记录出口 IP、ASN、延迟和冷却状态 |
| 邮箱域名池 | 自有域名/子域名导入、provider 绑定、连续拒绝阈值、自动拉黑、活跃数限制和手动重置 |
| 失败恢复 | 待处理 SSO / accounts 文本补录 CPA，跳过已有账号，成功后自动出队 |
| Docker 镜像 | Compose 一键运行；镜像内置 Camoufox、Xvfb 与浏览器依赖，`/data` 统一持久化 |
| 安全存储 | 代理、账号、SSO、日志、auth 与运行状态默认使用 owner-only 权限 |

## 界面预览

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/dashboard-dark.png">
  <img alt="Grok Register 注册控制台" src="docs/screenshots/dashboard-light.png">
</picture>

控制台集中展示任务参数、批次进度、时段成功率、账号补录和黑名单状态；图片会跟随 GitHub 的深浅主题自动切换。

## 架构示意

```text
┌─────────────────┐     HTTP proxy      ┌──────────────────┐
│  Camoufox 注册机 │ ──────────────────► │ 本地代理 mixed 口 │
│  (多 worker)     │   127.0.0.1:79xx    │ (可选链式 dialer) │
└────────┬────────┘                     └────────┬─────────┘
         │                                        │
         │ SSO / Device Flow                      ▼
         ▼                                 住宅出口 / 其它出口
   cpa_auth/ · grok2api_auth/
         │
         ▼
┌─────────────────┐
│ webui/monitor   │  读 log/register_results.jsonl · CPA 目录
│ :8787 Live 面板 │  启停 run_until_100 / run_batch_headless
│ + Bearer token  │  浏览器填「访问令牌」→ localStorage
└─────────────────┘
```

说明：**注册机本身只配置一层 HTTP 代理 URL**。若需要「先节点再家宽」等链式出口，在代理客户端（如 mihomo `dialer-proxy`）配置，对注册机透明。

## 快速开始

### Docker Compose（推荐）

镜像在构建时已经下载 Camoufox，不需要在宿主机安装 Python、Playwright 或 Xvfb：

```bash
git clone https://github.com/lij768423-svg/grok-register-panel.git
cd grok-register-panel
cp .env.example .env
# 编辑 .env，把 MONITOR_TOKEN 换成长随机串

docker compose up -d --build
docker compose logs -f panel
```

浏览器打开 `http://127.0.0.1:8787/`，在面板 Token 输入框填入 `.env` 中相同的
`MONITOR_TOKEN`。首次启动会从 `config.example.json` 初始化
`data/docker/config.json`，邮箱服务可直接在面板里保存和测试。

容器把以下内容统一保存在宿主机 `data/docker/`：

- `config.json`、`proxies.txt` 与 Next-Action 缓存
- `accounts/`、`cpa_auth/`、`grok2api_auth/`
- `log/` 中的运行日志、代理池、邮箱域名池和编排状态
- `accounts/imported_credentials.json` 中的导入账号库存（含明文密码，文件权限 `0600`）

停止或升级容器不会删除这些数据：

```bash
docker compose down
git pull
docker compose build --pull
docker compose up -d
```

发布版本可直接使用 GHCR 镜像：

```bash
GROK_REGISTER_IMAGE=ghcr.io/jackma15115/grok-register-panel:latest \
  docker compose pull
GROK_REGISTER_IMAGE=ghcr.io/jackma15115/grok-register-panel:latest \
  docker compose up -d
```

推送 `v*` Git 标签会由 GitHub Actions 自动构建并发布 `v0.2.1`、`0.2.1`、
`0.2` 和 `latest` 等标签；也可以在 Actions 页面手动运行 “Publish Docker image”。

### 源码运行环境（可选）

- Python 3.10+
- Linux 无头建议带 Xvfb；macOS 可本机 GUI/有头
- 能访问注册页、临时邮箱 API、`auth.x.ai` 的网络

### 源码安装

```bash
git clone https://github.com/lij768423-svg/grok-register-panel.git
cd grok-register-panel

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python -m camoufox fetch           # 必须：下载浏览器引擎（约数百 MB）

cp config.example.json config.json
# 编辑 config.json：邮箱、proxy、cpa_auth_dir 等
```

Debian/Ubuntu 无头运行还需要 Tk、Xvfb 和 xauth：

```bash
sudo apt-get install -y libtk8.6 xvfb xauth
```

> `pip install` 只装 Python 依赖；**不执行 `camoufox fetch` 无法启动浏览器**。

### 配置（`config.json`）

| 字段 | 说明 |
|------|------|
| `email_provider` | `cloudflare` / `duckmail` / `yyds` / `mailnest` / `cloudmail` / `moemail` / `ti-temp-mail` |
| `defaultDomains` | 临时邮域名（如二级 CF 域） |
| `cloudflare_*` / `duckmail_*` 等 | 对应邮箱 API |
| `moemail_api_base` | MoeMail 站点根 URL，例如 `https://mail.example.com` |
| `moemail_api_key` | MoeMail OpenAPI 的 `X-API-Key` |
| `moemail_domain` | 可选固定域名；留空时自动读取 `/api/config` 的可用域名 |
| `moemail_expiry_ms` | `3600000` / `86400000` / `604800000` / `0`，分别为 1 小时、1 天、7 天、永久 |
| `ti_temp_mail_base_url` | TI Temp Mail 站点根 URL，例如 `https://mail.example.com` |
| `ti_temp_mail_api_key` | 可选创建 Token；服务端未设置 `CREATE_TOKEN` 时留空 |
| `ti_temp_mail_domain` | 可选域名池，多个域名用逗号或分号分隔；留空时由服务端选择 |
| `ti_temp_mail_mode` | `maindomain`（主域名）或 `subdomain`（泛域名子域名） |
| `proxy` | 可选的旧版默认 HTTP 代理；留空时直连 |
| `proxies.txt` | 可选的旧版多行代理文件；未启用面板代理状态文件时继续兼容 |
| `register_workers` | 并发浏览器数（建议先 2～3） |
| `register_count` | 单次目标成功数；失败重试不占用成功名额 |
| `cpa_auto_add` | 是否 SSO→OAuth 并写入 auth |
| `cpa_auth_dir` | 本地 CPA 目录（`xai-*.json`） |
| `grok2api_auth_dir` | Grok2API 风格 auth 目录 |
| `cpa_remote_url` / `cpa_management_key` | 远程 CPA Management API（可选） |

### 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `MONITOR_TOKEN` | （空） | **必设**：面板写接口鉴权；未设时 start/stop/control 一律 401 |
| `MONITOR_HOST` | `127.0.0.1` | 面板绑定地址；**绑定失败不会回退到 `0.0.0.0`** |
| `MONITOR_PORT` | `8787` | 面板端口 |
| `PANEL_INCLUDE_TAIL` | `0` | `1` 时状态接口附带原始日志尾部（可能含敏感信息，默认关） |
| `CPA_AUTH_DIR` | `./cpa_auth` | 编排器 / 面板统计 CPA 数量 |
| `BATCH_LOG` | 自动发现最新 `log/batch*.log` | 面板跟踪的日志 |
| `BLACKLIST_STATE_FILE` | `./log/blacklist_state.json` | 运行时 ASN 黑名单状态 |
| `GROK_BATCH_IDLE_TIMEOUT` | `360` | batch 子进程连续无输出多少秒后自动重建（最小 60 秒） |
| `GROK_BATCH_MAX_RESTARTS` | `8` | 单批发生驱动崩溃或卡死时最多自动恢复次数 |
| `PROXY_POOL_STATE_FILE` | `./log/proxy_pool.json` | 外部代理池凭据、健康与冷却状态，文件权限 `0600` |
| `PROXY_NETWORK_COOLDOWN_SECONDS` | `90` | 运行时网络异常的短冷却秒数 |
| `PROXY_RISK_COOLDOWN_SECONDS` | `1800` | 注册风控后的长冷却秒数 |
| `EMAIL_PROVIDER_CONFIG_FILE` | `./config.json` | 面板邮箱服务配置文件；保存时保持 `0600` |
| `EMAIL_DOMAIN_POOL_STATE_FILE` | `./log/email_domain_pool.json` | 邮箱域名池状态与规则，文件权限 `0600` |
| `GROK_REGISTER_CONFIG_FILE` | `./config.json` | Docker 中为 `/data/config.json`；worker、面板和补录共用 |
| `ACCOUNT_LOGIN_STATE_FILE` | `./accounts/imported_credentials.json` | 导入账号私密库存；Docker 中持久化到 `/data/accounts/` |
| `MONITOR_MAX_REQUEST_BODY` | `16777216`（16 MiB） | 面板 JSON POST 请求体上限；导入账号数量不设条数上限，可按部署内存调高 |
| `NEXT_ACTION_CACHE_FILE` | `./.next_action_id.cache` | Docker 中持久化到 `/data/.next_action_id.cache` |
| `GROK_REGISTER_BROWSER_AUTO_FETCH` | `1` | 镜像内浏览器缓存缺失时自动补拉；正常构建的镜像已预装 |

生成 token 示例：

```bash
# Linux / macOS
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

### 跑起来

**A. 源码 Web 面板**

```bash
export MONITOR_TOKEN='你的长随机串'   # 必设，否则点启动会 401
export MONITOR_HOST=127.0.0.1         # 仅本机；局域网请改成具体网卡 IP
export MONITOR_PORT=8787
export CPA_AUTH_DIR=./cpa_auth
# 可选：需要页面里看原始日志尾时
# export PANEL_INCLUDE_TAIL=1

python webui/monitor.py
# 浏览器打开 http://127.0.0.1:8787/
```

1. 页面顶部 **控制** 区找到 **面板 Token** 输入框  
2. 填入与 `MONITOR_TOKEN` **相同**的字符串（自动写入 `localStorage`）  
3. 设模式 / workers / batch 数量 / 再跑 N / 风控满 N → **启动**
4. 需要多出口时打开顶部 **代理池**，导入代理并等待检测完成
5. 打开顶部 **邮箱服务**，选择 provider、填写对应参数，保存后执行一次连接测试
6. 需要多个自有收信域名轮换时，再展开 **域名轮换 · 高级设置** 导入域名并保存规则

也可在控制台手动写入：

```js
localStorage.setItem('MONITOR_TOKEN', '你的长随机串')
location.reload()
```

若未填 token 点启动，会看到：

```text
unauthorized: set MONITOR_TOKEN and pass Authorization: Bearer <token>
```

这是预期行为，不是注册链路崩溃。

**B. 命令行单批（无头 Linux）**

```bash
xvfb-run -a python -u run_batch_headless.py 20 3
#                        数量↑        并发↑
```

单批由独立监督进程运行。Playwright/Camoufox 驱动崩溃，或连续超过
`GROK_BATCH_IDLE_TIMEOUT` 没有输出时，监督进程会结束故障子进程并按原子进度文件
继续剩余数量；已经写入的账号、SSO 和 CPA 文件不会回滚。

**C. 编排器**

```bash
# 由面板写入 log/monitor_control.json（workers / add_count / risk_pause …）
python -u run_until_100.py
```

**D. GUI**

```bash
python grok_register_ttk.py
```

## Live 面板说明

### 控制

| 控件 | 作用 |
|------|------|
| **面板 Token** | 与环境变量 `MONITOR_TOKEN` 一致；启停/保存/重置黑名单必填 |
| 模式 Orch | 跑 `run_until_100.py` 多轮直到目标 CPA |
| 模式 单批 | 只跑一轮 `run_batch_headless` |
| workers | 并发浏览器 |
| batch 数量 | 单批账号数上限相关 |
| **再跑 N 个** | 从**当前** CPA 再注册 N 个（目标已满时点启动不会秒退） |
| 风控满 N 暂停 | 本轮注册风控达到 N 后停 batch 并分析 ASN |

### 鉴权约定

| 接口 | 鉴权 |
|------|------|
| `GET /` · `GET /api/health` | 可匿名；不返回运行数据 |
| `GET /api/status` · `/api/stats` · `/api/control` · `/api/blacklist` · `/api/recovery` · `/api/proxies` · `/api/email-domains` | 配置了 Token 后必须鉴权 |
| `POST /api/start` · `/api/stop` · `/api/control` · `/api/blacklist/reset` · `/api/recovery/*` · `/api/proxies/*` · `/api/email-domains/*` | 必须 `Authorization: Bearer <MONITOR_TOKEN>` |
| `PATCH /api/proxies/{id}` · `DELETE /api/proxies/{id}` · `PATCH/DELETE /api/email-domains/{id}` | 必须 `Authorization: Bearer <MONITOR_TOKEN>` |
| `GET /api/accounts/export-sso` · `GET /api/accounts/export-credentials-csv` | 必须 `Authorization: Bearer <MONITOR_TOKEN>`；未配置 Token 时也拒绝 |
| `GET /api/account-login` · `POST /api/account-login/*` | 始终要求有效 Token；GET 也不允许匿名，因为会返回完整邮箱地址 |

前端 `api()` 会从 Token 输入框 / `localStorage.MONITOR_TOKEN` / `window.MONITOR_TOKEN` 自动带头。

### 外部代理池

- 支持单条或批量粘贴 `http://user:pass@host:port`、`host:port:user:pass`，也兼容 HTTPS / SOCKS URL
- 导入时规范化并去重，随后后台并发探活；GET 接口轮询检测进度
- API 和 UI 只返回脱敏端点及 `has_auth`，不会返回代理账号或密码
- worker 只选择“健康 + 启用”的条目，并在每个新账号创建浏览器前热加载一次
- 一个账号从注册、SSO 到 OAuth 始终固定同一代理，不会中途更换出口
- 网络异常进入短冷却，注册风控进入长冷却；邮箱域名、验证码或邮箱 API 错误不处罚代理
- 面板池已有条目但没有健康代理时任务会明确停止，不会绕过状态回退到旧文件
- 面板池为零条目时 worker 明确走直连，不会回退到 `config.proxy` 或系统代理
- `proxies.txt` 可从界面导入；只有未启用面板代理状态文件的旧部署才兼容旧文件 / `config.proxy`

代理池不抓取、不分发公共代理，只管理操作者自己提供的外部代理。

### 邮箱服务与高级域名轮换

- 顶部“邮箱服务”统一配置 `cloudflare`、`duckmail`、`yyds`、`mailnest`、`cloudmail`、`moemail`、`ti-temp-mail`
- TI Temp Mail 支持可选创建 Token、`maindomain` / `subdomain` 模式和多域名随机选择；创建 Token 与邮箱访问 Token 分开使用
- 邮箱服务页显示脱敏后的 TI Temp Mail 收件日志；该区域不依赖 `PANEL_INCLUDE_TAIL`，也不会展示邮箱访问 Token
- 切换服务商时只显示该服务实际支持的字段；保存后新的注册任务读取 `config.json`
- 已保存的 API Key、JWT 和密码不会通过接口或页面回显；密钥输入留空会保留原值，必须点“清除”并保存才会删除
- “测试当前提供商”使用表单中的未保存内容做非破坏性连通性检查，不会改写 `config.json`
- `config.json` 以原子方式更新并保持 `0600`，现有无关配置项不会被覆盖

域名轮换位于邮箱服务页的高级设置中：

- 支持导入根域名或已有子域名，并绑定 `cloudflare`、`cloudmail`、`moemail`、`yyds`、`ti-temp-mail` provider
- 每个 provider 可设置最大活跃域名数；超出部分待命，活跃域名停用或拉黑后自动补位
- xAI 明确拒绝邮箱域名时累计连续失败，达到阈值后自动拉黑；成功提交邮箱后清零连续失败
- 邮箱 API、验证码超时和普通网络异常不会处罚域名，避免把基础设施故障误判成域名质量问题
- 通过“启用”“重置”“删除”管理条目；对应 provider 的面板池配置后，域名池耗尽不会回退旧配置
- `duckmail` 与 `mailnest` 的域名由上游服务分配，不能在面板中伪造自定义域名池

域名池只保存域名和运行统计，不保存邮箱账号密码或 provider 密钥。

### 时段成功率

基于 `log/register_results.jsonl`（纯 JSON Lines，无横幅污染）：

```text
成功率 = ok / (ok + fail + risk) × 100%
窗口：近 1 小时 / 3 小时 / 12 小时
```

### 黑名单

- 下号前解析出口 ASN，命中则换 sticky / 代理口  
- 编排器在风控累计到阈值后，对「几乎只有失败」的 ASN 扩黑  
- 自动扩展写入 `log/blacklist_state.json`，不会改写或执行 Python 源码
- 面板可 **刷新列表**；**重置** 为写操作，同样需要 Token  

### 账号补录

- **补录待处理**：读取 `accounts/sso_pending.txt`，跳过 CPA 已存在邮箱，成功一条立即原子出队
- **扫描全部账号**：扫描 `accounts/*.txt` 并对缺失 CPA 的记录执行转换，不删除原账号文件
- **导出 SSO**：汇总账号文件与 `sso_pending.txt`，去重后每行导出一个 SSO；明确排除 `sso_risk_rejected.txt`
- **导出账号 CSV**：导出 `email,passwd` 两列，使用 UTF-8 BOM 和标准 CSV 转义，便于表格软件直接打开
- 两个导出接口始终要求匹配 `MONITOR_TOKEN`，即使普通读取接口允许匿名也不会放宽
- 补录运行在独立子进程，面板可查看数量、上次结果和停止任务
- 命令行等价入口：

```bash
python sso_to_auth_json.py \
  --sso accounts/sso_pending.txt \
  --from-config config.json \
  --consume-success \
  --report-json log/recovery_report.json
```

### 导入账号管理

- 支持 `email----password`、`email,password`、`email:password` 和 Tab 分隔；CSV 可使用 `email,password` 或 `email,passwd` 表头。单次导入不设账号条数上限，仅受 `MONITOR_MAX_REQUEST_BODY` 请求体大小控制
- 导入时按邮箱去重；同邮箱密码变化会清除旧 SSO / CPA 状态并重新进入待处理
- “登录选中”只处理勾选账号；“登录待处理”会处理待处理、失败和已停止账号，开启 CPA 时也会重转已有 SSO
- 每个账号启动独立 Camoufox 会话，沿用面板健康代理池；登录成功写入 `accounts/{email}.txt` 的 `email----password----sso` 标准格式
- 开启“提取 CPA / Grok2API”后调用现有 SSO 转换配置；转换失败时保留 SSO，并显示为“SSO 已提取”供后续重试
- 账号登录、批量注册和账号补录互斥，避免并发争用浏览器与 auth 输出
- 库存文件是 owner-only 明文凭据文件；API 和表格只返回 `has_password`、`has_sso`、`cpa_ok`，不回传密码或 SSO 原文

## 工程实践备忘（非教程承诺）

以下为社区常见踩坑方向，**环境差异大，仅供参考**：

1. 邮箱：二级域名临时邮往往比批发一级域 / 大盘 Outlook·Google 更省事  
2. 出口：质量与冷却窗口影响大；同一出口短时间打太满容易抬失败率  
3. 风控字段：服务端 deny 后宜尽早结束 OAuth 路径  
4. 并发建议从 2～3 起跳，过高易空页、Turnstile 卡住、代理打满  
5. 「资料填写失败」有时是资料页人机未过，不一定是姓名密码写不进  
6. 链式代理在客户端配，不在注册机 Python 里写死  

## 目录结构

```text
.
├── grok_register_ttk.py       # GUI + CLI 主程序
├── register_flow.py           # 注册页流程 / Turnstile
├── browser_session.py         # 会话、出口探测、ASN 黑名单
├── sso_to_auth_json.py        # SSO → OAuth / 写 CPA（auth 文件 0600）
├── account_login_flow.py      # xAI 邮箱密码登录 / SSO 提取
├── account_login_worker.py    # 导入账号并发后台任务
├── camoufox_adapter.py
├── connectivity.py
├── run_batch_headless.py      # 无头批量（包根 Path 后 chdir）
├── run_until_100.py           # 编排器
├── webui/
│   ├── monitor.py             # Live 面板 HTTP 服务
│   ├── security_utils.py      # redact / token 校验
│   ├── blacklist_store.py     # 锁保护的 JSON 黑名单状态
│   ├── proxy_store.py         # 外部代理池、探活、冷却与脱敏视图
│   ├── email_domain_store.py  # 邮箱域名池、拒绝阈值与轮换状态
│   ├── process_utils.py       # 当前项目实例的进程发现 / 停止
│   ├── recovery_ops.py        # SSO / accounts 异步补录
│   ├── account_login_store.py # 私密导入账号库存 / 脱敏公开视图
│   ├── account_login_ops.py   # 导入、启动、停止和删除操作
│   └── blacklist_ops.py       # 面板黑名单接口
├── email_providers/
├── tests/                     # 结构 / 脱敏 / chdir 冒烟
├── scripts/                   # xvfb 辅助脚本
├── config.example.json
├── proxies.example.txt
├── requirements.txt
├── DEPLOYMENT.md
├── LICENSE · NOTICE
└── README.md
```

## 自检

```bash
# 无需 pytest；运行全部发布检查
PYTHON_BIN=.venv/bin/python scripts/run_tests.sh
```

部署前还应执行：

```bash
.venv/bin/python -m pip check
.venv/bin/python scripts/harden_runtime_permissions.py .
```

## 常见问题

**Q: 点启动报 `unauthorized: set MONITOR_TOKEN...`？**  
A: 服务端已启用写接口鉴权。启动 monitor 时 `export MONITOR_TOKEN=...`，浏览器 **面板 Token** 填同一串（或 `localStorage.setItem`）。硬刷新后再点启动。

**Q: 日志尾部显示 `raw log tail disabled`？**  
A: 默认关闭防泄密。需要时 `export PANEL_INCLUDE_TAIL=1` 后重启 `monitor.py`。

**Q: 点启动立刻结束？**  
A: CPA 已达旧目标。面板填大 **再跑 N 个** 再启动；编排器用 `add_count` 抬目标。

**Q: 全是「无法解析出口 IP」？**  
A: 打开顶部“代理池”查看异常和冷却原因，重新检测后只启用健康条目。旧版单代理仍可用 `curl -x http://127.0.0.1:端口 https://httpbin.org/ip` 单独探活。

**Q: 提示“面板代理池没有健康且启用的代理”？**
A: 导入项尚未检测、已停用、检测失败或仍在冷却。先在代理池页面执行“检测全部”；面板池已配置时不会回退复用旧文件中的坏代理。

**Q: 邮箱域名被自动拉黑，或域名池没有可用项？**
A: 只有 xAI 明确拒绝邮箱域名才会累计。打开“邮箱服务”并展开“域名轮换 · 高级设置”查看连续拒绝次数，确认 provider 与域名绑定正确；可手动重置或启用其它待命域名。邮箱 API、验证码超时不会触发域名拉黑。

**Q: 邮箱 API 401？**  
A: 打开“邮箱服务”检查对应 provider 的 Key / JWT / `auth_mode`，保存后点“测试当前提供商”。页面不会回显已保存密钥，输入框留空表示保留原值。

**Q: `Address already in use` / 面板打不开？**  
A: 8787 被其它进程占用（例如同机其它服务）。换 `MONITOR_PORT`，或先释放端口。绑定失败**不会**自动改绑 `0.0.0.0`。

**Q: Windows？**  
A: 主要在 macOS 与无界面 Linux 验证；Windows 需自备显示/依赖，欢迎 PR。

**Q: 面板和真实进程不一致？**  
A: 看 `log/orch100-stdout.log` 与最新 `log/batch-*.log`；欢迎提 issue / PR。

**Q: accounts 文本或待处理 SSO 怎么补录 CPA？**
A: 在控制台使用“账号补录”。待处理模式成功后自动出队；扫描全部账号模式会保留原始文本，并跳过本地 CPA 已存在邮箱。

## 安全

- **必须**设置 `MONITOR_TOKEN`；不要把 token 提交进仓库或贴进公开 issue  
- **不要提交** `config.json`、`accounts/`、`cpa_auth/`、`proxies.txt`、`log/proxy_pool.json`、`log/email_domain_pool.json`、真实 stickies、`log/monitor.token`
- `.gitignore` 已忽略上述路径  
- 运行数据、日志、PID、代理和账号文件使用 0600，父目录使用 0700
- API 响应带 CSP、禁止 iframe、安全类型与 Referrer Policy；请求体上限 64 KiB
- 停止任务只匹配当前项目根目录，不按全系统模糊命令行误杀
- 开源前自查：`grep -R api_key --include='*.json' .`（勿提交真实配置）  
- 面板默认**不**回传原始日志尾；生产环境固定 `PANEL_INCLUDE_TAIL=0`

## 更新记录（摘录）

| 提交方向 | 内容 |
|----------|------|
| 面板鉴权 | `MONITOR_TOKEN` + Bearer；UI 内 Token 输入；CORS 不开放 `*` |
| 绑定安全 | 失败不回退 `0.0.0.0`；默认 `PANEL_INCLUDE_TAIL=0` |
| 脱敏 | `webui/security_utils.py`；JSONL / 日志去凭据 |
| 路径 | `run_batch_headless` / blacklist 使用包相对 ROOT，无硬编码机器路径 |
| 稳定性 | `from __future__` 置顶；`Path` 先于 `chdir`；workers DOM id 拆分 |
| 结果流 | `register_results.jsonl` 仅 JSON 行 |

## 友情链接

- [LINUX DO](https://linux.do) — 新的理想型社区

## License

[MIT](LICENSE) — 见 [NOTICE](NOTICE) 对 AaronL725/grok-register 的归属说明。面板内嵌 Geist 字体使用 [SIL OFL 1.1](LICENSES/OFL-1.1-Geist.txt)。

## 致谢

- [Camoufox](https://camoufox.com/)
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) 等下游生态
- 上游 [AaronL725/grok-register](https://github.com/AaronL725/grok-register)
- 社区里分享风控字段与工程经验的各位

---

Star 鼓励一下 → https://github.com/lij768423-svg/grok-register-panel
