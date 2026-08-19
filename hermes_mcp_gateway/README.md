# 车间业务 MCP

这是 Cherry/Hermes 的只读适配层，不复制现有业务逻辑。生产推荐使用无数据库 MCP
模式：Cherry/Hermes 负责模型、会话记忆和知识库，本服务只负责鉴权、业务规则和简道云查询。

## 安装与启动

Linux 服务器先执行：

```bash
bash scripts/bootstrap_linux.sh
```

每个部门必须运行独立、受限的 MCP 进程。不要在两个智能体中共用无部门范围的 `hermes-welding-mcp`，否则模型可能看到不属于自己的工具。

Linux 服务器使用稳定入口启动：

```bash
export APP_ENV_FILE=/etc/welding-business-service/mcp.env
bash scripts/start_welding_mcp.sh
# 油漆部使用：bash scripts/start_painting_mcp.sh
```

也可以使用等价的模块入口：

```powershell
.\.venv\Scripts\python.exe -m hermes_mcp_gateway.server
```

Cherry/Hermes 的 MCP 类型选择 `stdio`。Linux 服务器命令填写：

```text
# 焊接部智能体
/opt/welding-business-service/.venv/bin/hermes-welding-mcp-welding

# 油漆部智能体
/opt/welding-business-service/.venv/bin/hermes-welding-mcp-painting
```

环境变量保留：

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

不要把 Cherry 的智能体工作目录当作项目导入路径；业务代码由已安装的
`hermes_mcp_gateway` 包和 `app` 包提供。这样本地 Cherry 与未来 Hermes
运行时都使用同一个进程入口和工具契约。

Windows 本地 Cherry 配置使用：

```powershell
.\start_welding_mcp.cmd
# 油漆部：.\start_painting_mcp.cmd
```

焊接 MCP 只提供：

- `get_welding_order_daily_report`
- `get_welding_work_report`
- `search_welding_knowledge`

油漆 MCP 只提供对应的 `get_painting_*` 和 `search_painting_knowledge` 工具。后端还会二次检查启动范围；焊接 MCP 调用油漆工具会被拒绝，即使 Cherry 的工具配置错误。

无数据库生产配置下，知识库工具由 Hermes 处理，MCP 知识库工具会明确返回已禁用，
不会连接 PostgreSQL。

报表、权限、数据适配器和知识检索仍然由 `app` 目录负责。
