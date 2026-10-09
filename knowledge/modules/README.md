# modules — 模块说明书索引

> 项目 llmwiki:每个模块一份理解文档。AI 读一个文件就理解一个模块——职责/数据模型/接口群/核心流程/状态机/依赖/关键实现/坑。
> 底账与接口/表全集在 `../API.md` / `../DATABASE.md`,说明书只写"理解与波及"。

| 模块 | 说明书 | 一句话职责 |
|---|---|---|
| M1 基础设施 | modules/M1-基础设施.md | 用户账号体系、项目(多仓库绑定/GitLab)、项目成员协作 |
| M2 平台设置 | modules/M2-平台设置.md | 平台设置页(GitLab/域名/全局参数/模型默认配置)单例配置 |
| M3 AI 能力 | modules/M3-AI能力.md | 模型接入(R13)+ 平台默认回退链(R23)+ MCP/Skills(R17) |
| M4 流程引擎 | modules/M4-流程引擎.md | 需求打磨→任务(dev/test/release)→发布→归档 主链路 |
| M5 执行环境 | modules/M5-执行环境.md | Runner 建容器 + 终端/预览/编辑器(容器内工作台) |
| M6 网关路由 | modules/M6-网关路由.md | 自研 Python 反代,Host 精确匹配 + WS 透传(R15) |
| M7 知识库 | modules/M7-知识库.md | 发布链自动归档(R14 条目)+ 项目文档空间(R20 快照) |
| M8 通知 | modules/M8-通知.md | 站内信中心 + 钉钉 webhook + 实时 toast(R18) |
| M9 权限审计 | modules/M9-权限审计.md | 平台角色双层 Guard + token_version + 审计日志(R19/R25) |
| M10 工作台 | modules/M10-工作台.md | Dashboard 汇总 + 四维管理聚合 + 平台导览/主题(R21/R22/R29/R30) |

## 消费顺序

- 新进项目/看全貌:`../INDEX.json` + `../REQUIREMENTS.md` + 本索引 → 逐模块说明书
- 改某模块:`modules/{模块名}.md` 开读,再按需下沉 `../API.md` / `../DATABASE.md`
- 若说明书与代码不符:以代码为准,回报 rd-knowledge 对账修订

> ⚠️ 本索引随首次建账生成;说明书逐个确认后落盘时更新此表对应行链接与职责文本。
