# welding-business-service 部署说明

本项目建议采用 **Git 仓库 + 云服务器拉取代码** 的方式部署。

当前推荐的生产边界是：

```text
Cherry（本地测试）/ Hermes（云端正式运行）
        │ 模型、意图识别、参数提取、会话记忆、知识库、最终回复
        ▼
welding-business-service MCP
        │ 鉴权、参数校验、确定性业务规则、简道云查询
        ▼
简道云业务数据
```

在这个模式下，业务 MCP 是无状态服务，订单和报工工具不需要 PostgreSQL。
数据库代码仍保留给可选的后台管理、权限管理、后端知识库和会话功能，不能把这些模块误认为当前 MCP 运行的硬依赖。

## 一、Git 仓库边界

仓库应包含：

- `app/`：业务服务、鉴权、简道云适配器和 API
- `hermes_mcp_gateway/`：Cherry/Hermes MCP 工具入口
- `alembic/`、`alembic.ini`：可选数据库迁移资产
- `pyproject.toml`、`scripts/`、`deploy/`：安装、启动和部署文件
- `tests/`：自动化测试
- `data/*_mock.json`：必要的本地测试夹具

仓库不得包含：

- `.env`、真实 Bot Secret、简道云 MCP 地址和企业微信凭据
- `.venv/`、`__pycache__/`、运行日志、缓存和本地数据库
- `data/generated_reports/`、`data/models/`、临时截图和调试文件

`.gitignore` 已经覆盖这些内容。提交前执行：

```bash
git status --short --ignored
git diff --check
```

如果真实密钥曾经进入过 Git 历史，不能只删除当前文件，必须立即轮换密钥并清理仓库历史。

## 二、服务器首次安装

以下命令适用于 Ubuntu/Debian 类 Linux 服务器。服务器需要预先安装 Git、Python 3.12 和 Python 虚拟环境组件：

```bash
sudo mkdir -p /opt
sudo chown "$USER":"$USER" /opt
git clone <你的私有仓库地址> /opt/welding-business-service
cd /opt/welding-business-service
bash scripts/bootstrap_linux.sh
```

不要把 `.venv` 从 Windows 上传到服务器。服务器必须使用 Linux 自己创建的虚拟环境。

## 三、无数据库 MCP 配置

复制模板到服务器受保护目录：

```bash
sudo install -d -m 750 /etc/welding-business-service
sudo cp deploy/mcp.env.example /etc/welding-business-service/mcp.env
sudo chmod 640 /etc/welding-business-service/mcp.env
sudo chown root:welding /etc/welding-business-service/mcp.env
```

编辑 `mcp.env`，至少填写：

- `JIANDAOYUN_MCP_URL`
- `JIANDAOYUN_WORKSHOP_APP_ID`
- `JIANDAOYUN_WORKSHOP_ENTRY_ID`
- `JIANDAOYUN_WORK_REPORT_ENTRY_ID`
- `JIANDAOYUN_WELDING_PICK_WORK_REPORT_ENTRY_ID`
- 两套报工表字段映射
- `WECOM_CORP_ID`、`WECOM_CORP_SECRET`（启用实时部门鉴权时必填）

确认配置：

```bash
set -a
. /etc/welding-business-service/mcp.env
set +a
export APP_ENV_FILE=/etc/welding-business-service/mcp.env
cd /opt/welding-business-service
.venv/bin/python scripts/check_mcp_config.py
```

检查通过后，MCP 可直接启动：

```bash
export APP_ENV_FILE=/etc/welding-business-service/mcp.env
bash scripts/start_mcp.sh
```

每个部门智能体必须配置独立 MCP Server，不能共用无范围的通用 `hermes-welding-mcp`。如果 Hermes 由平台负责启动 MCP，则分别配置：

```text
# 焊接部智能体
/opt/welding-business-service/.venv/bin/hermes-welding-mcp-welding

# 油漆部智能体
/opt/welding-business-service/.venv/bin/hermes-welding-mcp-painting
```

工作目录设置为 `/opt/welding-business-service`，环境变量设置为：

```text
APP_ENV_FILE=/etc/welding-business-service/mcp.env
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

MCP 使用 `stdio`，不需要为 MCP 单独开放公网端口。部门范围由专用启动入口固定：焊接入口不注册油漆工具，油漆入口不注册焊接工具；即使客户端错误调用，后端也会返回 403。

### Hermes + 腾讯云部署边界

腾讯云上的正式形态是 **Hermes 管理企业微信机器人、模型、会话记忆、知识库和最终答复**；本仓库只作为 Hermes 启动的只读业务 MCP。

- 不部署 `welding-business-api.service`，也不启动本项目的企业微信长连接。
- 不填写 `CHERRY_AGENT_*`，不需要部署 Cherry。
- MCP-only 环境不填写 `HERMES_AGENT_URL` 或 `HERMES_AGENT_API_KEY`；这是可选 HTTP/API 反向调用模式的配置，不是 Hermes 调用 MCP 所需的凭据。
- 保持所有 `*_WECOM_AIBOT_ENABLED=false`，并保持 `WORKSHOP_SCHEDULED_REPORT_ENABLED=false`，除非以后明确启用由本服务直连企业微信的定时推送。
- `WECOM_CORP_ID`、`WECOM_CORP_SECRET` 仍需填写：它们仅用于按 Hermes 传入的 `requester_id`/`chat_id` 实时校验员工部门，不用于机器人连接。Hermes 的 MCP 配置必须可靠地传入这些身份参数。

在 Hermes 中为每个部门配置一个独立的 stdio MCP Server：

```text
# 焊接部智能体
/opt/welding-business-service/.venv/bin/hermes-welding-mcp-welding

# 油漆部智能体
/opt/welding-business-service/.venv/bin/hermes-welding-mcp-painting
```

两者的工作目录均为 `/opt/welding-business-service`，环境变量均为：

```text
APP_ENV_FILE=/etc/welding-business-service/mcp.env
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

本地 Cherry 也按相同原则配置：焊接部智能体命令填写 `C:\Users\Administrator\Desktop\welding-business-service\start_welding_mcp.cmd`，油漆部智能体命令填写 `C:\Users\Administrator\Desktop\welding-business-service\start_painting_mcp.cmd`。两边都删除原先通用的 `hermes-welding-mcp.exe` MCP 配置，再断开并重新开启 MCP。

## 四、更新版本

服务器更新采用下面流程：

```bash
cd /opt/welding-business-service
git fetch origin
git checkout main
git pull --ff-only origin main
bash scripts/bootstrap_linux.sh
.venv/bin/python scripts/check_mcp_config.py
```

然后在 Hermes 中重启 MCP 进程，让它加载新的工具契约。不要复用旧 MCP 进程，否则新字段和新业务逻辑不会生效。

## 五、可选 API/企业微信长连接

当前推荐由 Hermes 负责企业微信通道、模型和会话。如果以后仍需要本项目承载 API 或企业微信 AIBot 长连接，再单独配置 `api.env` 并启动：

```bash
bash scripts/start_api.sh
```

仓库提供了 `deploy/systemd/welding-business-api.service` 作为 systemd 模板。这个可选 API 模式可能使用数据库中的平台管理、知识库或会话能力，不能与无数据库 MCP 模式混用配置。

## 六、安全要求

- 生产环境必须使用私有 Git 仓库。
- 服务器 Git 凭据使用部署密钥或只读 Deploy Key，不使用个人密码。
- 所有 Secret 放在服务器环境文件或云密钥管理服务中，不进 Git。
- `APP_ENV=production` 时实时企业微信部门鉴权必须可用；鉴权失败直接拒绝查询。
- `WORKSHOP_DEPARTMENT_ACCESS_MAP` 生产环境保持 `{}`，不使用开发环境通配权限。
- `WORKSHOP_ALLOW_MOCK_IN_PRODUCTION=false`，生产禁止模拟数据。
- `MODEL_ENABLED=false`，避免业务后端绕过 Hermes 调用模型。
- `MCP_KNOWLEDGE_TOOLS_ENABLED=false` 时，知识库由 Hermes 管理，MCP 不连接数据库。
- MCP 工具保持只读，不提供写入、删除、审批和修改订单的接口。

## 七、知识库上云

知识库属于 Hermes 的智能体能力，不放进 MCP 的实时业务查询链路。建议在 Hermes 中建立三个知识库：

- 共享知识库：上传 `knowledge/workshop/shared/`
- 焊接部知识库：上传 `knowledge/workshop/departments/welding/`
- 油漆部知识库：上传 `knowledge/workshop/departments/painting/`

焊接部智能体绑定共享库和焊接部库，油漆部智能体绑定共享库和油漆部库。订单、报工、人员和完成公分等实时数字必须调用 MCP 查询，不能依赖知识库中的静态文件。知识库内容更新时，先在 Git 中审核和提交，再在 Hermes 中重新上传或使用其同步能力更新。

## 八、可选：本服务直连企业微信的每天 08:30 定时日报

Hermes 一键连接企业微信的部署不启用本节功能：保持 `WORKSHOP_SCHEDULED_REPORT_ENABLED=false`，由 Hermes 自己处理机器人消息和定时能力。本节仅适用于以后明确需要由本服务持有独立企业微信 AIBot 凭据并直接向群发送日报的场景。

定时任务默认按 `Asia/Shanghai` 每天 08:30 运行，日报统计前一天。它分别生成焊接部、油漆部的订单日报 PNG 和报工日报 PNG，并向配置的企业微信群发送简短文字摘要和图片；不会发送 HTML 文件。HTML 会留存在 `data/generated_reports/workshop/scheduled/`，用于追溯和重新渲染。

在 `/etc/welding-business-service/mcp.env` 中填写真实 Bot 凭据、启用对应机器人，并把目标群 ID 替换为真实值：

```dotenv
WELDING_WECOM_AIBOT_BOT_ID=...
WELDING_WECOM_AIBOT_SECRET=...
WELDING_WECOM_AIBOT_ENABLED=true
PAINTING_WECOM_AIBOT_BOT_ID=...
PAINTING_WECOM_AIBOT_SECRET=...
PAINTING_WECOM_AIBOT_ENABLED=true
WORKSHOP_SCHEDULED_REPORT_TARGETS={"welding":["真实焊接群chatid"],"painting":["真实油漆群chatid"]}
```

安装并启用 timer：

```bash
sudo cp deploy/systemd/welding-business-scheduled-reports.service /etc/systemd/system/
sudo cp deploy/systemd/welding-business-scheduled-reports.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now welding-business-scheduled-reports.timer
systemctl list-timers welding-business-scheduled-reports.timer
```

上线前可以手动生成、不发送：

```bash
APP_ENV_FILE=/etc/welding-business-service/mcp.env scripts/run_scheduled_reports.sh --dry-run --date 2026-08-18
```

查看实际发送日志：

```bash
journalctl -u welding-business-scheduled-reports.service -n 200 --no-pager
```
