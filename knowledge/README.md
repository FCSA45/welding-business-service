# Hermes 知识库源文件

这个目录保存可审阅、可版本管理的知识库原始文件。它不是运行时数据库，也不会由
`welding-business-service` 自动读取或上传。

正式上云时，在 Hermes 中创建三类知识库并上传对应文件：

| Hermes 知识库 | 仓库来源目录 | 可被谁使用 |
| --- | --- | --- |
| 共享制度库 | `knowledge/workshop/shared/` | 焊接部、油漆部 |
| 焊接部专属库 | `knowledge/workshop/departments/welding/` | 仅焊接部智能体 |
| 油漆部专属库 | `knowledge/workshop/departments/painting/` | 仅油漆部智能体 |

上传前由业务负责人审核内容。禁止把简道云 Token、企业微信 Secret、员工身份证件、工资、
手机号或其他敏感信息写入知识文件。

知识库只用于制度说明、流程说明、术语和已审核的规则；订单、报工、人员产量、延期情况等
实时业务数据必须调用 MCP 工具查询，不能依赖知识库回答。
