# 部署指南

本文以 Docker Compose 为首选运行方式。镜像内置 Python、Camoufox、Xvfb 和浏览器
运行库；源码部署保留为调试或定制场景的可选方案。

## Docker Compose（推荐）

```bash
git clone https://github.com/lij768423-svg/grok-register-panel.git
cd grok-register-panel
cp .env.example .env
# 编辑 .env，至少替换 MONITOR_TOKEN

docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8787/api/health
```

生产部署要点：

- `MONITOR_TOKEN` 必须使用长随机值；Compose 在缺少该变量时会拒绝启动
- 容器内面板监听 `0.0.0.0:8787`，宿主机默认只绑定 `127.0.0.1:8787`；需要 LAN / Tailscale 访问时把 `.env` 的 `MONITOR_BIND_ADDRESS` 改成具体网卡 IP
- 浏览器和系统依赖在构建阶段进入镜像，运行时缓存缺失才会自动补拉
- Compose 默认使用 `linux/amd64`，让 Camoufox 在 ARM 主机上通过 Docker 模拟保持一致；确认目标版本原生支持后可覆盖 `DOCKER_PLATFORM`
- 默认挂载 `${GROK_REGISTER_HOST_DATA_DIR:-./data/docker}` 到 `/data`
- `/data` 包含配置、导入账号密码、SSO、CPA、Grok2API auth、日志、代理池和邮箱域名池，必须纳入私密备份
- 保留 `shm_size: 1gb` 与 `seccomp:unconfined`，否则多浏览器并发可能不稳定

首次启动会生成 `/data/config.json`。通过面板“邮箱服务”保存 TI Temp Mail 或其它
provider 后，新任务会直接读取该持久化配置。

更新：

```bash
docker compose down
git pull
docker compose build --pull
docker compose up -d
```

### GitHub Actions 发布

推送 `v*` 标签会触发 `.github/workflows/docker-publish.yml`，发布到
`ghcr.io/<owner>/<repo>`：

```bash
git tag v0.2.1
git push origin v0.2.1
```

工作流会发布完整版本、主次版本和 `latest` 标签，并附带 SBOM、provenance 和 OCI
元数据。也可以在 GitHub Actions 页面手动运行并指定 `edge` 等镜像标签。

仓库首次发布后，需要在 GitHub Packages 设置中确认镜像可见性符合部署要求。

本机自行发布到其它 registry 时设置仓库名后运行：

```bash
GROK_REGISTER_IMAGE=registry.example.com/team/grok-register-panel \
  scripts/publish_docker.sh
```

## 1. 源码安装（可选）

```bash
git clone https://github.com/lij768423-svg/grok-register-panel.git
cd grok-register-panel

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m camoufox fetch
```

`requirements.txt` 固定直接依赖版本；`requirements.lock.txt` 是发布环境的完整依赖快照。

验证：

```bash
.venv/bin/python -m pip check
.venv/bin/python -m camoufox version
```

## 2. 配置

```bash
cp config.example.json config.json
chmod 600 config.json
```

至少配置邮箱服务。需要自动写入 CPA 时，设置：

- `cpa_auto_add`
- `cpa_auth_dir`
- `grok2api_auth_dir`
- 可选的 `cpa_remote_url` 与 `cpa_management_key`

也可以在面板顶部打开“邮箱服务”，选择实际 provider 后填写、保存并测试连接。
面板只返回密钥是否已配置，不会回显 API Key、JWT 或密码；密钥输入留空会保留
原值，只有显式点“清除”并保存才会删除。连接测试使用当前表单内容但不会落盘。
配置仍写入 `config.json`，原子更新并保持 `0600`，其它已有配置项不会被覆盖。

代理池与 sticky 文件均属于凭据材料。运行权限脚本会将 `proxies*.txt`、
`stickies*.txt`、缓存文件及 `.env.monitor` 收紧为 `0600`。

面板“代理池”会把真实代理 URL 写入 `log/proxy_pool.json`，文件权限为 `0600`。
导入后先完成探活；有面板池条目时 worker 只使用健康且启用的代理，全部异常或
冷却时会停止对应任务。一个账号开始后，注册、SSO 与 OAuth 全程固定同一出口。

面板“邮箱服务”里的“域名轮换 · 高级设置”会把域名、provider、拒绝计数和轮换规则写入
`log/email_domain_pool.json`，文件权限为 `0600`。只有 xAI 明确拒绝邮箱域名时
才累计并按阈值拉黑；邮箱 API、验证码或网络异常不会处罚域名。对应 provider
池耗尽时 worker 会停止该任务，不会回退到已被停用或拉黑的旧域名配置。

## 3. 发布前检查

```bash
PYTHON_BIN=.venv/bin/python scripts/run_tests.sh
.venv/bin/python scripts/harden_runtime_permissions.py .
```

如果旧版本曾把自动 ASN 黑名单写入 `browser_session.py`，覆盖代码前先迁移：

```bash
.venv/bin/python scripts/migrate_legacy_blacklist.py \
  --source browser_session.py \
  --state log/blacklist_state.json
```

## 4. 临时启动面板

```bash
export MONITOR_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export MONITOR_HOST=127.0.0.1
export MONITOR_PORT=8787
export PANEL_INCLUDE_TAIL=0
export CPA_AUTH_DIR="$PWD/cpa_auth"
# 可选：覆盖代理池状态位置与冷却时间
# export PROXY_POOL_STATE_FILE="$PWD/log/proxy_pool.json"
# export PROXY_NETWORK_COOLDOWN_SECONDS=90
# export PROXY_RISK_COOLDOWN_SECONDS=1800
# 可选：覆盖邮箱域名池状态位置
# export EMAIL_DOMAIN_POOL_STATE_FILE="$PWD/log/email_domain_pool.json"

.venv/bin/python -u webui/monitor.py
```

局域网或 Tailscale 部署时，将 `MONITOR_HOST` 设置为目标网卡的具体 IP；不要使用 `0.0.0.0`。浏览器打开面板后，在“访问令牌”输入与环境变量相同的值。

## 5. systemd 持久运行

复制并按实际用户和目录修改：

```bash
sudo cp deploy/grok-register-panel.service.example /etc/systemd/system/grok-register-panel.service
sudo cp deploy/monitor.env.example /etc/grok-register-panel.env
sudo chmod 600 /etc/grok-register-panel.env
sudo systemctl daemon-reload
sudo systemctl enable --now grok-register-panel.service
```

服务必须满足：

- `UMask=0077`
- `PANEL_INCLUDE_TAIL=0`
- 绑定具体 loopback、LAN 或 Tailscale IP
- `MONITOR_TOKEN` 使用至少 32 字节随机值
- `Restart=on-failure`

验证：

```bash
systemctl status grok-register-panel.service --no-pager
curl http://目标地址:8787/api/health
curl -o /dev/null -w '%{http_code}\n' http://目标地址:8787/api/status
curl -H "Authorization: Bearer $MONITOR_TOKEN" http://目标地址:8787/api/status
```

第二条状态接口在未带 Token 时应返回 `401`。

## 6. 运行任务

单批：

```bash
xvfb-run -a .venv/bin/python -u run_batch_headless.py 20 3
```

辅助脚本：

```bash
scripts/run_xvfb_smoke.sh 1
scripts/run_xvfb_batch.sh 10
```

持续编排建议从面板启动；停止操作只会结束当前项目目录下的编排和批处理进程。

## 7. 账号补录

面板的“账号补录”支持：

- `sso_pending.txt` 补录，成功后立即出队
- 扫描全部 `accounts/*.txt`
- 跳过本地 CPA 已存在邮箱
- 停止正在运行的补录进程
- 导出全部可用 SSO（包含 `sso_pending.txt`，排除风控拒绝记录）
- 导出 `email,passwd` 两列的 UTF-8 CSV

两个导出按钮和对应的 `GET /api/accounts/export-*` 接口始终要求有效的
`Authorization: Bearer <MONITOR_TOKEN>`，没有配置 Token 时也不会开放下载。

命令行：

```bash
.venv/bin/python sso_to_auth_json.py \
  --sso accounts/sso_pending.txt \
  --from-config config.json \
  --consume-success \
  --report-json log/recovery_report.json
```

## 8. 导入账号管理

面板的“导入账号管理”支持粘贴 `email + password`，启动 Camoufox 登录并提取 SSO。
Docker 会把库存保存到 `/data/accounts/imported_credentials.json`，把任务和报告保存到
`/data/log/`。库存文件包含明文密码，必须保持 `0600`、只做加密或受控备份。
单次导入不限制账号条数，默认 POST 请求体为 16 MiB；需要更大批次时设置
`MONITOR_MAX_REQUEST_BODY`（例如 `67108864` 表示 64 MiB）。

开启“提取 CPA / Grok2API”时，worker 继续使用 `/data/config.json` 中的
`cpa_auth_dir`、`cpa_remote_url` 和 `grok2api_auth_dir`。登录任务与注册、账号补录任务互斥。
`GET /api/account-login` 与所有 `/api/account-login/*` 写接口始终要求有效
`MONITOR_TOKEN`；响应不会包含密码或 SSO 原文。

## 9. 安全边界

- `/api/health` 和静态页面可匿名访问；运行数据 API 在配置 Token 后要求鉴权。
- 不要通过公网裸露内置 HTTP 服务。公网访问应放在有 TLS 和额外身份认证的反向代理后。
- 生产环境不要启用原始日志尾部。
- 不要把 Token 写入 URL、命令行参数、仓库或 issue。
- 代理池 API 不返回账号密码，但 `log/proxy_pool.json` 本身含真实凭据，备份与迁移时按密钥材料处理。
- 邮箱域名池不保存邮箱账号密码，但 `log/email_domain_pool.json` 仍属于运行状态，迁移时保留 `0600` 权限。
- 面板使用内置 HTTP 服务，适合单机、LAN 或 tailnet 运维，不替代互联网边界网关。
