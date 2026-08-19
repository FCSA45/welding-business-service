# 车间智能体业务模块代码说明

> 多部门接入统一使用 `department_report_service.py`；部门规则与知识文件位于
> `knowledge/workshop/departments/`。详细步骤见 `docs/部门机器人接入指南.md`。

## 本目录负责什么

| 文件 | 职责 |
|---|---|
| `manifest.py` | 智能体身份，以及只能读取 `workshop`、`shared` 知识域的规则 |
| `models.py` | 车间订单、工序、异常、日报等标准数据格式和数据校验 |
| `adapters.py` | mock/简道云使用统一接口，并禁止生产环境误用 mock |
| `mock_source.py` | 无真实 ERP/MES 接口时读取并校验模拟工序数据 |
| `process_repository.py` | 内容寻址去重；数据变更时新增版本并保留历史 |
| `yesterday_report.py` | 按报工时间筛选昨日数据，计算数量、米数、优先级和部门分组 |
| `report_repository.py` | 保存不可随意修改的报表快照；内容变化时生成新版本 |
| `report_presentation.py` | 把报表数据组装成 HTML 和飞书卡片 |
| `report_delivery.py` | 生成 PNG、上传飞书、发送卡片，并记录成功或失败 |

## 公开调用方式

- 数据接入：`build_workshop_adapter(settings).fetch_records()`，再交给 `WorkshopProcessImporter.import_records()`。
- 报表计算：只能使用 `WorkshopProcessImporter.list_current(department)` 返回的当前 DWD 明细；`department` 必须先在 handler/service 层完成权限校验，不得在报表函数中直接请求简道云。
- 报表推送：只能通过带 `X-API-Key` 的 `/api/v1/workshop-reports/{report_id}/deliveries` 调用。

## 禁止直接调用

- API 层不允许直接调用 `mock_source.load_mock_process_records()`。
- 智能体注册文件不允许访问 `app.db.models` 或扫描数据库。
- `report_presentation.py` 只能负责数据转 UI，不允许修改统计结果。

## 哪些代码故意不放在这里

- `app/agents/workshop/manifest.py`：多智能体平台的注册和知识权限入口。
- `app/api/workshop_reports.py`：全项目统一管理 HTTP 接口和鉴权。
- `app/db/models.py`：全项目共用同一套数据库基础和表关系。
- `app/feishu/client.py`：所有智能体复用飞书鉴权、上传和发消息能力。
- `app/reports/image_renderer.py`：所有智能体复用 HTML 转 PNG 能力。
- `alembic/versions/`：数据库升级文件必须按全项目顺序统一管理。

这些不是代码散乱，而是明确的公共底座。车间智能体通过接口使用公共底座，不能自己复制一套。
