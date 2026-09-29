# PRD:项目详情页聚合改版

> 创建日期:2026-09-29
> 状态:已确认(2026-09-29 两轮访谈收口,用户进入 /rd-plan 视为确认;待确认清单为空)
> 输入:用户口述 + 现状摸底(ProjectDetail.tsx 五平铺 Tab、dashboard 仅个人口径、无项目维度聚合接口)

## 背景与目标

现状项目详情页(`/projects/{id}`)是 5 个平铺 Tab(需求/任务/仓库/成员/设置),无任何聚合视图:产品/成员想看「项目整体进展到哪了」需要逐个 Tab 数。工作台 dashboard 只有「与我相关」个人口径,没有项目维度。

目标:项目详情页以**聚合概览为默认主视图**——需求、开发、测试、发布四维 + 统计数据一屏呈现;完整列表与管理动作保留可达。成功标准:打开项目即了解全局进度,无需逐 Tab 查。

## 用户故事

1. 作为项目成员,我希望打开项目详情就看到需求/开发/测试/发布的数量与状态分布,以便快速评估项目健康度
2. 作为项目成员,我希望从概览直达最近活跃的需求/任务详情,以便跟进最新动态
3. 作为 owner,我希望仓库/成员/设置等管理动作集中在一处,不与日常进度视图混杂

## 需求点清单

### R1:项目聚合统计接口 `GET /api/projects/{project_id}/summary`

- **描述**:项目维度聚合统计,单请求返回概览页全部数据
- **触发场景**:概览 Tab 加载/刷新(唯一消费方)
- **前置条件**:登录用户;项目可见性沿用现有规则(private 非成员 404,internal 非成员不可见)
- **边界定义**:
  - 做什么:四维统计(需求/开发/测试/发布)、token 统计、近 7 天活跃、最近发布摘要、最近需求/任务 Top5
  - 不做什么:时间自由筛选;效率类指标(时长均值/准时率);跨项目对比;事件流
- **字段定义**(响应 data 建议结构,终稿由 rd-arch/rd-plan 定):
  | 字段 | 类型 | 说明 |
  |---|---|---|
  | requirements | object | `{total, by_status(8 态零填充), active}`(active=polishing+reviewing;打磨任务数单列 `polish_tasks`) |
  | dev_tasks / test_tasks / release_tasks | object | `{total, by_status(8 态零填充), active}`(active=running+starting+cases_review 口径由 plan 定) |
  | tokens | object | `{total, by_type: {dev, test, release, requirement}}`(null 不计) |
  | recent_7d | object | `{requirements_created, requirements_completed, tasks_created, tasks_completed}` |
  | latest_release | object\|null | `{task_id, title, status, branch, preview_url, finished_at}`(取最近一条 release 任务;无则 null) |
  | recent_requirements | array[≤5] | `{req_id, title, status, priority, delivery_date, updated_at}`(按 updated_at 倒序) |
  | recent_tasks | array[≤5] | `{task_id, type, title, status, finished_at, updated_at}`(按最近活动倒序) |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 非成员访问 private 项目 | 404(沿项目可见性) | 前端既有 404 处理 |
  | 空项目(无需求无任务) | 各统计零值、latest_release=null、recent 数组空 | 不报错 |
  | by_status 口径 | 复用 dashboard `_by_status_zero_filled` 先例,8 态零填充 | 与列表页计数可对账 |
  | 近 7 天口径 | now-7d 自然日滚动,平台时区 | — |
- **依赖**:无(全新接口)
- **异常与边界场景**:大数据量(千级任务)性能由 plan 关注(单请求 <1s 量级);统计排除软删/异常数据口径与列表页一致
- **验收标准**:
  1. 概览页单请求拿到全部统计数据
  2. 各状态计数与需求/任务列表页实况一致(可对账)
  3. private 非成员 404;空项目零值不报错

### R2:概览 Tab(默认首屏)——统计区 + 四维区块 + 最近列表

- **描述**:项目详情页默认 Tab 改为「概览」,承载聚合主视图
- **触发场景**:进入项目详情页
- **前置条件**:R1 接口就绪;项目成员(含 viewer,读侧全员可见)
- **边界定义**:
  - 做什么:
    - **统计区**(`累计 / 近 7 天` 两口径切换):① 需求卡(总数+打磨任务数+状态分布迷你条+进行中高亮)② 开发任务卡 ③ 测试任务卡 ④ 发布任务卡(附最近发布:分支/环境状态/预览链接;空态「暂无发布记录,创建发布任务后展示」)⑤ token 卡(总量+四类占比;in/out 进 tooltip)⑥ 近 7 天纯数字组(新增需求 X · 完成需求 Y · 新增任务 A · 完成任务 B)
    - **需求区块**:最近需求 Top5 行(标题/状态徽章/优先级/交付日期/相对更新时间)+「查看全部」
    - **任务区块**:最近任务 Top5 行(类型徽章/标题/状态徽章/短 id/相对时间)+「查看全部」
  - 不做什么:逐日图表(二期);效率指标(二期);自由时间筛选;改需求/任务详情页
- **字段定义**:
  | 位置 | 字段 | 来源 |
  |---|---|---|
  | 维度卡 | total / by_status / active | R1 requirements·dev_tasks·test_tasks·release_tasks |
  | token 卡 | total / by_type / (in,out tooltip) | R1 tokens |
  | 近 7 天 | 4 个计数 | R1 recent_7d |
  | 需求行 | title/status/priority/delivery_date/相对 updated_at | R1 recent_requirements |
  | 任务行 | type/title/status/短 id/相对时间 | R1 recent_tasks |
  | 发布卡 | branch/环境状态/preview_url | R1 latest_release |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 区块「查看全部」 | 切到需求/任务 Tab | 对应 Tab |
  | 最近列表行点击 | 跳既有详情路由 | 需求/任务详情页 |
  | 发布卡预览链接 | 新窗口打开 | preview_url |
  | 口径切换(累计/近 7 天) | 仅统计区数字切换,区块列表不变 | — |
  | 接口失败 | 区块级错误条 + 重试(照页面既有错误条模式) | — |
- **依赖**:R1
- **异常与边界场景**:加载中骨架屏;空项目各区块空态;长标题截断;delivery_date 已过期/临期是否高亮→不做(二期效率范畴)
- **验收标准**:
  1. 默认进入项目详情落在概览 Tab
  2. 四卡/近 7 天数字与列表页实况一致(累计口径可对账)
  3. 查看全部跳转、行点击跳详情、发布卡预览链接可打开
  4. 口径切换仅影响统计区
  5. 空项目/接口失败降级正常

### R3:Tab 架构调整(概览 | 需求 | 任务 | 管理)

- **描述**:Tab 集从 5 个改 4 个:概览(新,默认)| 需求(现状保留)| 任务(现状保留)| 管理(新增,内含 仓库/成员/设置 三个子 Tab)
- **触发场景**:页面导航
- **前置条件**:R2 概览存在(默认 Tab 切换依赖它)
- **边界定义**:
  - 做什么:Tab 重组;「管理」Tab 内子 Tab 直接复用现有 RepoManagement/MemberManagement/设置三组件(零改造);需求/任务 Tab 原组件原功能保留
  - 不做什么:需求/任务列表组件功能演进;删除任何现有能力
- **字段定义**:无新增
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 进入页面 | 默认落概览 Tab | — |
  | 原「设置」深链/入口 | 重定向到 管理 Tab 对应子 Tab | 兼容旧入口 |
- **依赖**:R2
- **异常与边界场景**:管理 Tab 权限与原设置 Tab 一致(写操作后端校验不变)
- **验收标准**:
  1. 4 Tab 结构正确,默认落概览
  2. 管理内三子 Tab 功能回归与原 Tab 一致
  3. 需求/任务 Tab 回归零变化

## 非功能需求

- summary 单请求;千级任务量级响应目标 <1s(优化手段归 plan)
- 统计读侧项目全员可见(含 viewer);写操作既有后端校验不变;private 非成员 404 不变

## 范围外

- 工作台 dashboard 页(个人口径)与独立任务列表页不改
- 需求/任务详情页不改
- 移动端适配
- 事件流 activity(需事件埋点,宜单独立项)
- 效率类指标(时长均值/准时率)——二期
- 逐日活跃图表——二期
- 自由时间范围筛选

## 设计稿引用

无(无外部设计稿;沿用 DESIGN.md / vp 设计体系)

## 待确认清单

- [ ] (空——两轮访谈已收口;summary 响应字段终稿与 active 口径由 rd-arch/rd-plan 定稿)
