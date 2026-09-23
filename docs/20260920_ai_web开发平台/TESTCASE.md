# UI 专项走查 · 测试用例清单

> **本轮范围**:UI 专项走查(视觉 + 基础交互);边界/异常类不在本轮(已由 rd-check 接口断言覆盖)。
> **用户指令**:页面 UI 不合适/错位的一律提 bug 后自动修复。
> **参数化路由取数**:在用例「前置」列标注「从列表页取首个真实 id 现场替换」的用例,执行时从对应列表页获取真实 id 后替换 URL 参数。
> **用例编号规则**:TC-{R{n}}-{序号};类型 = 主流程 / 视觉 / 交互。

> 2026-09-22 UI 专项走查执行完毕:详见 .scratch/test-results/ 与 BUGS.md
> 2026-09-23 期望值按 vp/index.html 修正(OVERREACH 36 条),详见 .scratch/rd-test/triage.md

---

## R1 用户与账号体系

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R1-01 | 主流程 | /login | 登录页可达,居中卡片布局,含 Logo+标题+表单 | 无 | ✅ | — | — |
| TC-R1-02 | 视觉 | 登录页卡片 | `.card` width=400px (`max-w-md`) | /login | ✅ | — | — |
| TC-R1-03 | 视觉 | 登录页卡片 | 垂直居中 (`flex items-center justify-center min-h-screen`) | /login | ✅ | — | — |
| TC-R1-04 | 视觉 | 表单 label | position: 输入框上方 | /login | ✅ | — | — |
| TC-R1-05 | 视觉 | 错误提示 | position: 输入框下方(提交触发校验后) | /login 输入错误密码提交 | ⏭ | — | — |
| TC-R1-06 | 视觉 | 登录按钮 | width: 全宽 (`w-full`) | /login | ✅ | — | — |
| TC-R1-07 | 视觉 | 登录按钮 | 背景色 `bg-primary` (#18181b);文字色 `text-white` (#ffffff) | /login | ✅ | — | — |
| TC-R1-08 | 视觉 | 标题 | font-size: 17px | /login | ✅* | BUG-UI-007 | report/TC-R1-01-login-page.png | (期望已按 vp 修正 2026-09-23) |
| TC-R1-09 | 视觉 | 登录卡片圆角 | border-radius: 16px | /login | ✅* | BUG-UI-008 | report/TC-R1-01-login-page.png | (期望已按 vp 修正 2026-09-23) |
| TC-R1-10 | 视觉 | label | font-size: `text-sm` (0.875rem) | /login | ✅ | — | — |
| TC-R1-11 | 视觉 | 按钮/输入框 | border-radius: `rounded-md` (0.5rem) | /login | ✅ | — | — |
| TC-R1-12 | 视觉 | 卡片 | border-radius: 16px;padding: 26px | /login | ✅* | BUG-UI-009 | report/TC-R1-01-login-page.png | (期望已按 vp 修正 2026-09-23) |
| TC-R1-13 | 视觉 | 表单项间距 | gap: 14px | /login | ✅* | BUG-UI-010 | report/TC-R1-01-login-page.png | (期望已按 vp 修正 2026-09-23) |
| TC-R1-14 | 视觉 | 按钮 hover | hover 背景 `bg-[#27272a]` | /login 鼠标悬停按钮 | ✅* | BUG-UI-011 | report/TC-R1-01-login-page.png | (期望已按 vp 修正 2026-09-23) |
| TC-R1-15 | 视觉 | 输入框 focus | 双层 ring (`--ring-offset` + `--ring`) + `border-ring` | /login 聚焦输入框 | ✅* | BUG-UI-012 | report/TC-R1-01-login-page.png | (期望已按 vp 修正 2026-09-23) |
| TC-R1-16 | 视觉 | 过渡效果 | transition: `transition-all`,时长 0.15s | /login 交互元素 | ✅* | BUG-UI-011 | report/TC-R1-01-login-page.png | (期望已按 vp 修正 2026-09-23) |
| TC-R1-17 | 交互 | /register | 注册页可达,表单字段完整(手机号/密码/确认密码) | 无 | ✅ | BUG-UI-013 | report/TC-R1-17-register-page.png |
| TC-R1-18 | 交互 | /forgot-password | 找回密码页可达,含手机号输入+发送按钮 | 无 | ⏭(V2 预留) | BUG-UI-014 | report/TC-R1-18-forgot-password-page.png |
| TC-R1-19 | 交互 | /reset-password | 重置密码页可达,含新密码+确认密码表单 | 从找回密码流程跳转 | ⏭(V2 预留) | BUG-UI-015 | report/TC-R1-19-reset-password-page.png |
| TC-R1-20 | 交互 | /settings/profile | 个人信息设置页可达,显示当前用户信息 | 已登录 | ✅ | — | report/TC-R1-20-profile-settings-page.png |
| TC-R1-21 | 交互 | /settings/gitlab-token | GitLab Token 设置页可达,含 Token 输入+保存按钮 | 已登录 | ✅ | — | report/TC-R1-21-gitlab-token-settings.png |

---

## R2 项目管理(绑定 GitLab,支持多仓库)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R2-01 | 主流程 | /projects | 项目列表页可达,含页标题+状态徽章+.pcards>.pcard 卡片网格(vp L860-886) | 已登录 | ✅* | BUG-UI-020 | report/TC-R2-01-card-layout.png | (期望已按 vp 修正 2026-09-23) |
| TC-R2-02 | 视觉 | 项目列表 Table | column-width: 自适应 | /projects | ⏭ | — | — |
| TC-R2-03 | 视觉 | 操作列 | width: 固定 150px | /projects | ⏭ | — | — |
| TC-R2-04 | 视觉 | 对话框 | width: 500px;position: 居中 | 打开新建项目对话框 | ✅ | — | — |
| TC-R2-05 | 视觉 | 项目列表(卡片网格) | `.pcards>.pcard` 卡片网格,非 `<table>`;无 table 行 hover(vp L860-886) | /projects | ✅* | BUG-UI-016 | report/TC-R2-05-hover-no-bg-change.png | (期望已按 vp 修正 2026-09-23) |
| TC-R2-06 | 视觉 | Dialog 动画 | 淡入淡出 + 缩放 (0.95 → 1) | 打开/关闭对话框 | ✅* | BUG-UI-018 | report/TC-R2-06-dialog-no-animation.png | (R18 补建后回归通过 2026-09-23) |
| TC-R2-07 | 视觉 | 空态文案 | 文案="还没有项目 · 创建项目或等待邀请"(vp L1651) | /projects 无数据时 | ✅* | BUG-UI-019 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R2-08 | 视觉 | 项目卡片结构 | 卡片 foot 仅 av-stack+badge,无操作按钮(vp L860-886) | /projects | ✅* | BUG-UI-020 | report/TC-R2-08-card-layout.png | (期望已按 vp 修正 2026-09-23) |
| TC-R2-09 | 视觉 | 仓库列表列结构 | 列: 角色徽章 / 仓库 URL / 绑定方式 / 绑定时间 / 操作(解绑) | /projects/:id 仓库 Tab | ⚠️ | — | report/TC-R2-09-repo-management.png |
| TC-R2-10 | 交互 | /projects/:projectId | 项目详情页可达,含 Tab 导航(概览/设置等) | 从列表页取首个真实 id 现场替换 | ⚠️ | — | report/TC-R2-10-tab-navigation.png |
| TC-R2-11 | 交互 | 新建项目对话框 | 打开/关闭正常;表单含名称/描述/仓库 URL 等字段 | /projects | ✅ | — | report/TC-R2-11-project-create-form.png |

---

## R3 需求管理与打磨

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R3-01 | 主流程 | /projects/:projectId/requirements | 需求列表页可达,含页标题+状态/优先级徽章+.card 包裹 Table | 从项目列表取首个真实 id 现场替换 | ✅ | — | — |
| TC-R3-02 | 视觉 | 需求列表 Table | 列: 需求/状态/优先级/分支/创建人/更新时间(vp L927) | 需求列表页 | ✅* | BUG-UI-024 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R3-03 | 视觉 | 需求详情页页头 | 固定 (position: sticky/fixed);含标题+状态徽章+优先级徽章+操作按钮 | /requirements/:reqId | ✅ | — | — |
| TC-R3-04 | 视觉 | 需求详情页内容区 | 可滚动;基本信息卡片含背景/描述/验收标准 Markdown 渲染 | /requirements/:reqId | ✅* | BUG-019/BUG-020/BUG-021 | — | (期望已按 vp 修正 2026-09-23;BUG-020/BUG-021 OVERREACH;BUG-019 fixed+verified) |
| TC-R3-05 | 视觉 | 状态徽章样式 | draft=outline / polishing=secondary / reviewing=primary / approved=success / in_progress=primary / done=success / archived=outline / rejected=danger | 需求列表含各状态数据 | ✅ | — | — |
| TC-R3-06 | 视觉 | 优先级徽章样式 | low=outline / medium=secondary / high=primary | 需求列表含各优先级数据 | ✅ | — | — |
| TC-R3-07 | 视觉 | 任务类型徽章样式 | requirement=secondary / dev=primary / test=primary / release=success | 需求详情关联任务列表 | ✅* | BUG-UI-026 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R3-08 | 视觉 | 需求列表列结构 | 列: 标题 / 状态徽章 / 优先级徽章 / 创建人 / 创建时间 / 操作(查看/编辑/删除) | 需求列表页 | ✅* | BUG-UI-025 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R3-09 | 视觉 | 关联任务列表列结构 | 列: 任务类型徽章 / 标题 / 状态徽章 / 创建时间 / 操作(查看) | 需求详情页 | ✅ | — | — |
| TC-R3-10 | 交互 | /requirements/:reqId | 需求详情页可达,含编辑/开始打磨/提交评审/评审通过/驳回等操作按钮(vp L1053-1061) | 从列表页取首个真实 id 现场替换 | ✅* | BUG-022 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R3-11 | 交互 | 编辑需求对话框 | 打开/关闭正常;含标题/描述/优先级/验收标准字段;approved 状态显示"创建开发任务"按钮(vp L1053) | 需求列表页 | ✅* | BUG-023 | — | (期望已按 vp 修正 2026-09-23) |

---

## R4 任务(统一执行单元)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R4-01 | 主流程 | /tasks/:taskId | 任务工作台可达,三栏布局(左文件树+中编辑器+右对话框) | 从需求详情取首个任务 id 现场替换 | ✅ | — | — |
| TC-R4-02 | 视觉 | 任务工作台 layout | 三栏布局: 左侧文件树 width=250px 固定;右侧对话框 width=400px 固定;中间编辑器 width=自适应 | /tasks/:taskId | ✅ | — | — |
| TC-R4-03 | 视觉 | 页面头部 | 含标题+类型徽章+状态徽章+操作按钮(停止/重试) | /tasks/:taskId | ✅ | — | — |
| TC-R4-04 | 视觉 | 中间编辑器区 | 上半 Monaco 编辑器+下半 Diff 视图/预览 iframe | /tasks/:taskId | ✅ | — | — |
| TC-R4-05 | 视觉 | 右侧活动流面板 | 含活动流 Tab(vp L1453)+终端 Tab | /tasks/:taskId | ✅* | BUG-UI-028 | report/TC-R4-05-no-activity-tab.png | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R4-06 | 视觉 | 对话框结构 | 消息列表+输入框+附件按钮 | /tasks/:taskId | ✅ | — | — |
| TC-R4-07 | 交互 | 文件树 Tab 切换 | 「全部文件」/「变更文件」Tab 切换正常,变更文件 Tab 显示变更数徽标 | /tasks/:taskId | ✅* | BUG-UI-027 | report/TC-R4-07-no-badge.png | (期望已按 vp 修正 2026-09-23) |
| TC-R4-08 | 交互 | 对话框消息发送 | 输入消息→发送→消息列表追加;附件按钮可上传文件 | /tasks/:taskId | ✅* | BUG-024 | report/TC-R4-08-send-failure.png | (R18 补建后回归通过 2026-09-23) |

---

## R5 开发任务(type=dev)

> 无独立视觉断言源(复用 R4 工作台布局)。

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R5-01 | 主流程 | /tasks/:taskId(dev 类型) | 开发任务工作台可达,布局同 R4 | 从任务列表取 type=dev 的 id 现场替换 | ✅ | — | — |
| TC-R5-02 | 交互 | @filename 自动补全 | 对话框输入 `@` 触发已上传文件自动补全列表 | /tasks/:taskId(dev) | ✅* | BUG-UI-029 | report/TC-R5-02-no-autocomplete.png | (R18 补建后回归通过 2026-09-23) |
| TC-R5-03 | 交互 | 文件变更双视图 | 「全部」/「变更」视图切换正常;变更视图显示 M/A/D/R 徽标+行数标注 | /tasks/:taskId(dev) | ⏭ | — | — |

---

## R6 测试任务(type=test)

> 无独立视觉断言源(复用 R4 工作台布局)。

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R6-01 | 主流程 | /tasks/:taskId/cases | 用例审阅页可达,标题"测试用例审阅",含操作栏+用例 Table | 从任务列表取 type=test 的 id 现场替换 | ✅ | — | — |
| TC-R6-02 | 主流程 | /tasks/:taskId/report | 测试报告页可达,标题"测试报告",含统计卡片+用例 Table | 同 TC-R6-01 前置 | ✅ | — | — |
| TC-R6-03 | 视觉 | 统计卡片(报告页) | 4 张卡片: 总用例数 / 通过数 / 失败数 / 通过率 | /tasks/:taskId/report | ✅ | — | — |
| TC-R6-04 | 视觉 | 用例列表列结构(审阅页) | 列: 用例标题 / 步骤 / 预期结果 / 操作(编辑/删除) | /tasks/:taskId/cases | ✅ | — | — |
| TC-R6-05 | 视觉 | 用例列表列结构(报告页) | 列: 用例标题 / 状态徽章 / 日志(可展开) | /tasks/:taskId/report | ✅ | — | — |
| TC-R6-06 | 视觉 | 徽章样式 | passed=success / failed=danger | 报告页含执行结果数据 | ⏭ | — | — |
| TC-R6-07 | 交互 | 审阅页操作栏 | "新增用例"按钮打开对话框;"开始执行"按钮(primary)触发执行;用例以 `<table class="tbl">` 表格展示,非内联表单(vp L1299-1313) | /tasks/:taskId/cases | ✅* | BUG-UI-030 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R6-08 | 交互 | 报告页操作栏(failed) | "接受失败"(secondary)+"驳回回开发"(primary)按钮可见可点 | /tasks/:taskId/report 含失败用例 | ⏭ | — | — |

---

## R7 发布任务(type=release)

> 无独立视觉断言源(引用 R4)。

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R7-01 | 主流程 | /tasks/:taskId/deploy | 部署状态页可达,含状态卡片+部署日志(只读) | 从任务列表取 type=release 的 id 现场替换 | ✅* | BUG-025 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R7-02 | 视觉 | 状态卡片 | 含部署 URL(可点击)/ 状态徽章(deploying=primary / deployed=success / failed=danger)/ 部署时间 | /tasks/:taskId/deploy | ✅* | BUG-025 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R7-03 | 视觉 | 部署日志 | Textarea 只读,等宽字体 | /tasks/:taskId/deploy | ✅* | BUG-025 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R7-04 | 交互 | 下线按钮 | deployed 状态下显示"下线"按钮(danger),点击触发下线 | /tasks/:taskId/deploy 已部署 | ✅* | BUG-025 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R7-05 | 交互 | 创建发布任务对话框 | deploy_port+deploy_host 输入框(默认预填 `{slug}.{deploy_base_domain}`)+deploy_script(可选)+实时 URL 预览 | 需求详情页创建发布任务 | ✅* | BUG-025 | — | (期望已按 vp 修正 2026-09-23) |

---

## R8 任务级容器(执行沙箱,Runner 架构)

> 无视觉断言源(纯后端/Runner 逻辑,无前端页面)。

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R8-01 | 主流程 | (无前端页面) | 本需求点无前端 UI,跳过 | — | ⏭ | — | — |

---

## R9 Web 终端(实时 TTY)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R9-01 | 主流程 | /tasks/:taskId 终端区 | 终端区可达,含 Tab 栏(vp L1438)+xterm.js 全宽渲染 | 从任务列表取首个 id 现场替换 | ✅* | BUG-UI-031 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R9-02 | 视觉 | 终端区(xterm.js) | width: 全宽;height: 自适应 | /tasks/:taskId 终端区 | ✅ | — | — |
| TC-R9-03 | 视觉 | 终端背景 | 颜色 `#1e1e1e`(深色) | /tasks/:taskId 终端区 | ✅ | — | — |
| TC-R9-04 | 视觉 | 终端字体 | font-family: `--font-mono`(vp L238/240) | /tasks/:taskId 终端区 | ✅* | BUG-UI-032 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R9-05 | 视觉 | 空态 | 文案="点击新建终端" | /tasks/:taskId 无终端时 | ✅ | — | — |
| TC-R9-06 | 交互 | 终端 Tab 切换 | 多个终端 Tab 切换正常,每个 Tab 独立 shell session | /tasks/:taskId 新建多个终端 | ⏭ | — | — |
| TC-R9-07 | 交互 | 新建终端按钮 | 右侧"新建终端"按钮点击后新增 Tab+xterm 实例 | /tasks/:taskId | ⏭ | BUG-UI-033 | — |

---

## R10 实时预览(仅任务内)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R10-01 | 主流程 | /tasks/:taskId 预览区 | 预览区可达,含操作栏+iframe 全宽渲染 | 从任务列表取首个 id 现场替换 | ⏭ | — | — |
| TC-R10-02 | 视觉 | 预览区(iframe) | width: 全宽;height: 自适应 | /tasks/:taskId 预览区 | ⏭ | — | — |
| TC-R10-03 | 视觉 | 操作栏 | 右侧"在新窗口打开"按钮(outline,vp 无 filled 规格) | /tasks/:taskId 预览区 | ✅* | BUG-UI-034 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R10-04 | 视觉 | 空态 | 文案="服务未启动" | /tasks/:taskId 服务未启动时 | ✅ | — | — |
| TC-R10-05 | 视觉 | 加载失败 | Alert 组件显示"加载失败,请重试或查看终端日志" | 预览加载失败时 | ⏭ | — | — |
| TC-R10-06 | 交互 | 在新窗口打开 | 点击按钮在新标签页打开预览 URL | /tasks/:taskId 预览区 | ⏭ | — | — |

---

## R11 在线编辑器(双模式)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R11-01 | 主流程 | /tasks/:taskId 编辑器区 | 编辑器区可达,左侧文件树(250px)+右侧 Monaco 编辑器(自适应) | 从任务列表取首个 id 现场替换 | ⏭ | — | — |
| TC-R11-02 | 视觉 | 文件树 | width: 250px 固定 | /tasks/:taskId 编辑器区 | ✅ | — | — |
| TC-R11-03 | 视觉 | 编辑器 | width: 自适应;Monaco 主题 `vs-dark` | /tasks/:taskId 编辑器区 | ⏭ | — | — |
| TC-R11-04 | 视觉 | 文件树字体 | font-family: `--font-sans` | /tasks/:taskId 文件树 | ✅ | — | — |
| TC-R11-05 | 视觉 | 顶部 Tab 栏 | 已打开文件 Tab 列表,可切换/关闭 | /tasks/:taskId 打开多文件 | ⏭ | — | — |
| TC-R11-06 | 视觉 | 底部状态栏 | 显示当前文件路径/编码/行列号 | /tasks/:taskId 打开文件 | ⏭ | — | — |
| TC-R11-07 | 视觉 | 变更文件 Tab | 按仓库分组的扁平列表,每行=变更类型徽标(M/A/D/R)+文件路径+行数标注(`+X/-Y`) | /tasks/:taskId 有变更时 | ✅ | — | — |
| TC-R11-08 | 交互 | 项目详情页代码 Tab | /projects/:projectId 代码 Tab 可达,Monaco 只读模式+分支选择器(默认 master) | 从项目列表取首个 id 现场替换 | ⏭ | — | — |
| TC-R11-09 | 交互 | 文件树操作 | 支持增删改查/重命名/拖拽(任务工作台模式) | /tasks/:taskId | ⏭ | — | — |

---

## R12 项目成员与协作

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R12-01 | 主流程 | /projects/:projectId 成员 Tab | 成员管理 Tab 可达,含操作栏+成员 Table | 从项目列表取首个 id 现场替换 | ✅ | — | — |
| TC-R12-02 | 视觉 | 成员列表 Table | column-width: 自适应;操作列 width: 固定 150px | 成员 Tab | ✅ | — | — |
| TC-R12-03 | 视觉 | 对话框 | width: 500px;position: 居中 | 打开邀请/改角色/移除对话框 | ✅ | — | — |
| TC-R12-04 | 视觉 | 成员列表列结构 | 列: 头像+用户名(带昵称副标题)/ 角色徽章(owner=primary/editor=secondary/viewer=outline)/ 邀请人 / 加入时间 / 操作(改角色/移除) | 成员 Tab | ✅ | — | — |
| TC-R12-05 | 视觉 | owner 行 | 「移除」按钮禁用(最后一个 owner) | 成员 Tab 含 owner | ✅ | — | — |
| TC-R12-06 | 交互 | 邀请成员对话框 | 手机号输入+角色 Select(editor/viewer)+取消/邀请按钮;打开关闭正常 | 成员 Tab | ✅ | — | — |
| TC-R12-07 | 交互 | 改角色/移除对话框 | 改角色: 当前角色(只读)+新角色 Select+取消/确定;移除: 提示文案+取消/确定 | 成员 Tab | ✅ | — | — |

---

## R13 模型接入(项目级 url+key)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R13-01 | 主流程 | /projects/:projectId 模型 Tab | 模型配置 Tab 可达,含操作栏+配置 Table | 从项目列表取首个 id 现场替换 | ✅ | — | — |
| TC-R13-02 | 视觉 | 配置列表 Table | column-width: 自适应;操作列 width: 固定 200px | 模型 Tab | ✅ | — | — |
| TC-R13-03 | 视觉 | 对话框 | width: 500px;position: 居中 | 打开新建/编辑配置对话框 | ✅ | — | — |
| TC-R13-04 | 视觉 | 配置列表列结构 | 列: 配置名(带 default 徽章)/ base_url / model / api_key(打码)/ 状态徽章(enabled/disabled)/ 创建人 / 创建时间 / 操作(编辑/删除/测试) | 模型 Tab | ✅ | — | — |
| TC-R13-05 | 视觉 | default 行 | 「删除」按钮禁用 | 模型 Tab 含 default 配置 | ✅ | — | — |
| TC-R13-06 | 视觉 | Badge 样式 | default=primary / enabled=secondary / disabled=outline | 模型 Tab | ✅ | — | — |
| TC-R13-07 | 视觉 | api_key 输入框 | type=password,placeholder="sk-xxx",右侧眼睛图标切换明文/密文 | 新建配置对话框 | ✅ | — | — |
| TC-R13-08 | 交互 | 新建/编辑配置对话框 | 含配置名/base_url/api_key/model/is_default/enabled 字段;「测试连接」按钮(secondary)+取消/保存 | 模型 Tab | ✅ | — | — |
| TC-R13-09 | 交互 | 删除确认对话框 | 提示「确定删除配置 {name} 吗?」+取消/确定 | 模型 Tab 点击删除 | ✅ | — | — |

---

## R14 归档与知识库

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R14-01 | 主流程 | /requirements/:reqId/archive | 归档页可达,含需求信息卡片+时间线+归档总结+关联知识 Table | 从需求列表取首个 id 现场替换 | ✅ | — | — |
| TC-R14-02 | 主流程 | /projects/:projectId/knowledge | 项目知识库页可达,含操作栏(.fbar, vp L358)+知识卡片网格 | 从项目列表取首个 id 现场替换 | ✅* | BUG-UI-035 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R14-03 | 主流程 | /knowledge | 平台知识库页可达,含操作栏(.fbar)+知识卡片网格 | 已登录 | ✅ | — | — |
| TC-R14-04 | 视觉 | 归档页时间线 | 垂直排列;节点间距 16px | /requirements/:reqId/archive | ✅ | — | — |
| TC-R14-05 | 视觉 | 知识库卡片网格(≥1280px) | 每行 3 列 | /knowledge 视口≥1280px | ✅ | — | — |
| TC-R14-06 | 视觉 | 知识库卡片网格(≥768px) | 每行 2 列 | /knowledge 视口≥768px | ✅ | — | — |
| TC-R14-07 | 视觉 | 知识库卡片网格(<768px) | 每行 1 列 | /knowledge 视口<768px | ✅ | — | — |
| TC-R14-08 | 视觉 | 归档页需求信息卡片 | 含标题/状态徽章(archived)/创建人/创建时间 | /requirements/:reqId/archive | ⏭ | — | — |
| TC-R14-09 | 视觉 | 关联知识条目列结构 | 列: 类型徽章 / 标题 / 标签 / 状态徽章(draft=outline/published=success)/ 操作(查看/发布) | /requirements/:reqId/archive | ⏭ | — | — |
| TC-R14-10 | 视觉 | 知识卡片结构 | 每卡片: 类型徽章+标题+描述(前 100 字)+标签徽章+状态徽章+创建时间 | /knowledge | ✅ | — | — |
| TC-R14-11 | 视觉 | Badge 样式 | type: code_snippet=primary / pattern=secondary / pitfall=danger / doc=outline | /knowledge | ✅ | — | — |
| TC-R14-12 | 视觉 | .fbar 筛选栏 | 含搜索框+类型/标签过滤 Select+新建条目按钮(vp L358) | /knowledge | ✅* | BUG-UI-035,BUG-UI-036 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R14-13 | 交互 | Tab 导航(项目级) | 项目知识库 / 平台知识库 Tab 切换正常 | /projects/:projectId/knowledge | ✅ | — | — |
| TC-R14-14 | 交互 | 分页器 | 底部居中,翻页正常 | /knowledge 数据>1 页 | ⏭ | — | — |

---

## R15 平台网关与域名(网关直连 Runner)

> 无视觉断言源(纯后端/网关基础设施,无前端页面)。

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R15-01 | 主流程 | (无前端页面) | 本需求点无前端 UI,跳过 | — | ⏭ | — | — |

---

## R16 Runner 管理(分布式容器执行)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R16-01 | 主流程 | /admin/runners | Runner 管理页可达,含页标题「Runner 管理」+操作栏+Runner Table | 超管登录 | ✅ | — | — |
| TC-R16-02 | 视觉 | Runner 列表 Table | column-width: 自适应;操作列无固定宽度(vp L1573) | /admin/runners | ✅* | BUG-UI-037 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R16-03 | 视觉 | 新建/重置对话框 | width: 500px;position: 居中 | 打开新建 Runner 对话框 | ✅ | — | — |
| TC-R16-04 | 视觉 | 创建成功对话框 | width: 600px;position: 居中;含 token(等宽字体可复制)+启动命令示例(bash 代码块) | 创建 Runner 成功后 | ⏭ | — | — |
| TC-R16-05 | 视觉 | offline 行 | 灰显 `opacity-50` | /admin/runners 含 offline Runner | ⏭ | — | — |
| TC-R16-06 | 视觉 | Runner 列表列结构 | 列: 名称 / 角色徽章(worker=secondary/deploy=primary)/ 状态徽章(online=success/offline=secondary/disabled=outline)/ 当前容器数 / 机器信息(CPU/内存)/ 最后心跳 / 操作(重置 token/禁用/删除) | /admin/runners | ✅ | — | — |
| TC-R16-07 | 视觉 | 新建 Runner 对话框表单 | 名称 Input+角色 Select(worker/deploy)+最大容器数 Input(type=number,default=10);deploy 时条件显示公网 IP Input | 打开新建对话框 | ✅ | — | — |
| TC-R16-08 | 交互 | 角色 Select 联动 | 切到 deploy 时显示公网 IP 输入框;切回 worker 时隐藏 | 新建 Runner 对话框 | ✅ | — | — |
| TC-R16-09 | 交互 | Token 复制 | 创建成功后 token 显示框点击复制到剪贴板 | 创建 Runner 成功后 | ⏭ | — | — |

---

## R17 MCP server 与 Skills 管理

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R17-01 | 主流程 | /projects/:projectId MCP Tab | MCP 配置 Tab 可达,含 JSON 编辑器+保存按钮+底部提示文案 | 从项目列表取首个 id 现场替换 | ✅ | — | — |
| TC-R17-02 | 主流程 | /projects/:projectId Skills Tab | Skills 管理 Tab 可达,含操作栏+已安装 Skills Table | 同 TC-R17-01 前置 | ✅ | — | — |
| TC-R17-03 | 主流程 | /admin/skills | 平台级 Skills 市场页可达(超管) | 超管登录 | ✅ | — | — |
| TC-R17-04 | 视觉 | JSON 编辑器 | width: 全宽;字体: 等宽字体(Monaco/Geist Mono);行数: 20 行 | MCP Tab | ✅ | — | — |
| TC-R17-05 | 视觉 | Skills 列表 Table | column-width: 自适应;操作列 width: 固定 150px | Skills Tab | ✅ | — | — |
| TC-R17-06 | 视觉 | Skills 列表列结构 | 列: Skill 名 / 描述 / 来源徽章(platform=secondary/project=primary)/ 安装人 / 安装时间 / 操作(查看/卸载) | Skills Tab | ✅ | — | — |
| TC-R17-07 | 视觉 | 底部提示文案 | 文案="配置将注入到任务容器的 `~/.claude/config.json`" | MCP Tab | ✅ | — | — |
| TC-R17-08 | 交互 | 使用模板对话框 | 模板卡片列表→参数表单→"生成"按钮;打开关闭正常 | MCP Tab | ✅ | — | — |
| TC-R17-09 | 交互 | 从市场安装对话框 | 平台级 Skills 卡片列表+"安装"按钮 | Skills Tab | ✅ | — | — |
| TC-R17-10 | 交互 | 上传自定义 Skill 对话框 | 文件上传 Input(accept=".md")+取消/上传按钮 | Skills Tab | ✅ | — | — |

---

## R18 站内信与通知

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R18-01 | 主流程 | /notifications | 通知中心页可达,含页标题+操作栏+通知 Table+分页器 | 已登录 | ✅* | BUG-UI-038 | — | (R18 补建后回归通过 2026-09-23) |
| TC-R18-02 | 主流程 | /settings/notifications | 通知设置页可达,含钉钉通知卡片+实时通知卡片 | 已登录 | ✅* | BUG-UI-039 | — | (R18 补建后回归通过 2026-09-23) |
| TC-R18-03 | 视觉 | 通知列表 Table | column-width: 自适应;操作列 width: 固定 150px | /notifications | ✅* | BUG-UI-040 | — | (R18 补建后回归通过 2026-09-23) |
| TC-R18-04 | 视觉 | 通知列表列结构 | 列: 级别徽章(critical=danger/normal=primary/info=outline)/ 标题 / 内容(前 100 字)/ 项目(若有)/ 时间 / 状态(未读加粗)/ 操作(查看/删除) | /notifications | ✅* | BUG-UI-038 | — | (R18 补建后回归通过 2026-09-23) |
| TC-R18-05 | 视觉 | 未读通知行 | 加粗 `font-semibold` | /notifications 含未读通知 | ✅* | BUG-UI-039 | — | (R18 补建后回归通过 2026-09-23) |
| TC-R18-06 | 视觉 | 通知设置卡片 | width: 自适应;含 webhook 输入框+启用 Switch+"测试"按钮(secondary)+"保存"按钮(primary) | /settings/notifications | ✅* | BUG-UI-040 | — | (R18 补建后回归通过 2026-09-23) |
| TC-R18-07 | 视觉 | 导航栏铃铛 | 铃铛图标+未读红点+计数;点击下拉显示最近 5 条未读+"查看全部" | 已登录含未读通知 | ✅* | BUG-UI-038 | — | (R18 补建后回归通过 2026-09-23) |
| TC-R18-08 | 视觉 | 实时 toast | 右下角弹出,5s 自动消失,从右下角滑入 | 触发实时通知 | ⏭ | — | — |
| TC-R18-09 | 交互 | 分类 Tab 切换 | 全部/告警/任务/项目 Tab 切换正常;未读过滤 Switch 切换正常 | /notifications | ✅* | BUG-UI-040 | — | (R18 补建后回归通过 2026-09-23) |
| TC-R18-10 | 交互 | 全部已读按钮 | 点击后所有通知变为已读状态 | /notifications 含未读 | ✅* | BUG-UI-038 | — | (R18 补建后回归通过 2026-09-23) |

---

## R19 平台角色与权限体系

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R19-01 | 主流程 | /admin/users | 用户管理页可达,含筛选栏+工具栏+用户 Table+分页器 | 超管登录 | ✅ | — | — |
| TC-R19-02 | 主流程 | /admin/audit-logs | 审计日志页可达,含筛选栏+日志 Table+分页器 | 超管登录 | ✅ | — | — |
| TC-R19-03 | 视觉 | 平台管理导航分组 | role=superadmin 时存在;role=user 时不存在 | 左侧导航 | ✅ | — | — |
| TC-R19-04 | 视觉 | 用户列表-手机号列 | 文本格式 `138****5678` 形式(打码) | /admin/users | ✅ | — | — |
| TC-R19-05 | 视觉 | 角色徽章-superadmin | 样式 b-blue(vp L499) | /admin/users | ✅* | BUG-UI-041 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R19-06 | 视觉 | 状态徽章-disabled | 样式 danger 系 | /admin/users 含 disabled 用户 | ⏭ | — | — |
| TC-R19-07 | 视觉 | 邀请 token 文本 | 字体 `--font-mono` | 邀请新用户对话框 | ✅ | — | — |
| TC-R19-08 | 视觉 | 审计操作者 superadmin 徽章 | operator_role=superadmin 时存在 | /admin/audit-logs | ⏭ | — | — |
| TC-R19-09 | 视觉 | 分页器 | 默认页大小 20 | /admin/users 和 /admin/audit-logs | ✅ | — | — |
| TC-R19-10 | 视觉 | 禁用确认对话框文案 | 含"立即失效"与"取消"字样 | 点击禁用按钮 | ✅ | — | — |
| TC-R19-11 | 视觉 | 审计日志列结构 | 列: 时间 / 操作者(昵称+superadmin 徽章)/ 操作类型 / 项目 / 目标 / 详情(JSON 摘要,悬浮全量,最大宽度 320px 溢出省略)/ IP | /admin/audit-logs | ⚠️ | — | — |
| TC-R19-12 | 视觉 | 空态文案 | 审计="暂无符合条件的日志";用户="暂无用户" | 无数据时 | ⚠️ | — | — |
| TC-R19-13 | 视觉 | 筛选栏布局 | flex row + wrap, gap 8px, padding 12px 16px(vp L1611: `.fbar{gap:8px;padding:12px 16px}`) | /admin/users 和 /admin/audit-logs | ✅* | BUG-UI-042 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R19-14 | 交互 | 用户筛选 | 状态下拉(全部/正常/已禁用)+搜索框(手机号/昵称,防抖 300ms)筛选正常 | /admin/users | ✅ | — | — |
| TC-R19-15 | 交互 | 审计日志筛选 | 时间范围(DateRangePicker,默认最近 7 天)+用户下拉(可搜索)+操作类型下拉+查询按钮 | /admin/audit-logs | ⚠️ | — | — |

---

## R20 项目知识库管理

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R20-01 | 主流程 | /projects/:projectId/knowledge | 知识库列表 Tab 可达,含操作栏+卡片网格(3 列) | 从项目列表取首个 id 现场替换 | ✅ | — | — |
| TC-R20-02 | 主流程 | /projects/:projectId/knowledge-bases/:kbId | 知识库阅读页可达,含顶部栏+左树(260px)+右内容区 | 从知识库列表取首个 id 现场替换 | ⏭ | — | — |
| TC-R20-03 | 视觉 | 左树面板 | width: 260px | 阅读页 | ⏭ | — | — |
| TC-R20-04 | 视觉 | 阅读页内容区 | max-width: 860px;居中;padding: 24px 32px | 阅读页 | ⏭ | — | — |
| TC-R20-05 | 视觉 | 树节点 | height: 32px;padding-left 按层级 16px 递进 | 阅读页树形目录 | ⏭ | — | — |
| TC-R20-06 | 视觉 | 树节点 hover | background-color: `--color-surface-strong`(#f4f4f5) | 阅读页鼠标悬停树节点 | ⏭ | — | — |
| TC-R20-07 | 视觉 | 选中树节点 | font-weight: 500;background-color: `--color-surface-strong` | 点击树节点 | ⏭ | — | — |
| TC-R20-08 | 视觉 | 类型徽章-目录导入 | 文本="目录导入";source_type=repo_import 时显示 | 知识库列表 | ⏭ | — | — |
| TC-R20-09 | 视觉 | 同步徽章-导入中 | 图标 Loader2 转动(w-3 h-3);import_status=importing 时显示 | 知识库列表导入中 | ⏭ | — | — |
| TC-R20-10 | 视觉 | repo_import 编辑入口 | source_type=repo_import 时隐藏(不存在) | 阅读页 repo_import 类型 | ⏭ | — | — |
| TC-R20-11 | 视觉 | Monaco 主题(编辑态) | 值=vs-dark | 阅读页编辑态 | ⏭ | — | — |
| TC-R20-12 | 视觉 | 代码块渲染 | 含代码块的页面高亮渲染正常 | 阅读页含代码块页面 | ⏭ | — | — |
| TC-R20-13 | 视觉 | 资源未导入占位 | 相对路径图片显示"资源未导入(仅导入 .md 文本)" | 阅读页含图片页面 | ⏭ | — | — |
| TC-R20-14 | 视觉 | 顶部栏 | border-bottom: 1px `--color-border`(#e4e4e7);height 48px | 阅读页 | ⏭ | — | — |
| TC-R20-15 | 视觉 | 卡片样式 | `.card`(shadcn Card, rounded-lg + shadow-sm + p-6) | 知识库列表 | ✅ | — | — |
| TC-R20-16 | 视觉 | 空态文案 | 列表="暂无知识库";阅读页="暂无页面,点击\"新建页面\"开始" | 无数据时 | ✅ | — | — |
| TC-R20-17 | 交互 | 新建知识库对话框 | 类型 Radio(空模板/目录导入)→空模板=名称+描述;目录导入=名称+描述+仓库下拉+分支下拉+目录多选 | 知识库列表 | ✅ | — | — |
| TC-R20-18 | 交互 | 树形目录拖拽 | blank 类型知识库支持拖拽排序页面节点 | 阅读页 blank 类型 | ⏭ | — | — |

---

## R21 全局 Dashboard(我的工作台)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R21-01 | 主流程 | / | Dashboard 可达,含问候语+统计卡片区(4 列)+四组列表区(2 列) | 已登录 | ✅ | — | — |
| TC-R21-02 | 视觉 | 页面容器 | max-width: 1200px;居中;padding: 16px(vp L348) | / | ✅* | BUG-UI-044 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R21-03 | 视觉 | 统计卡片区 | grid-template-columns: 4 列(≥1280px) | / 视口≥1280px | ✅ | — | — |
| TC-R21-04 | 视觉 | 统计卡片 | padding: 16px(p-4) | / | ✅ | — | — |
| TC-R21-05 | 视觉 | 列表行 padding | padding: 9px 16px(vp L1611: `.dlist-row{padding:9px 16px}`) | / | ✅* | BUG-UI-045 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R21-06 | 视觉 | 统计卡片 hover | background-color: #f4f4f5 | / 鼠标悬停统计卡片 | ✅ | — | — |
| TC-R21-07 | 视觉 | 状态分布 mini 徽章 | 仅显示值>0 的状态 | / | ✅ | — | — |
| TC-R21-08 | 视觉 | 列表行 | gap: 8px;padding: 12px 16px(vp L1611: `.fbar{gap:8px;padding:12px 16px}`) | / | ✅* | BUG-UI-048 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R21-09 | 视觉 | 列表行 border-bottom | 1px #e4e4e7(末行无) | / | ✅* | BUG-UI-046 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R21-10 | 视觉 | 列表行 hover | background-color: #f4f4f5 | / 鼠标悬停列表行 | ✅ | — | — |
| TC-R21-11 | 视觉 | 每类列表条数 | ≤5 | / | ✅ | — | — |
| TC-R21-12 | 视觉 | 无项目页面级空态 | 文案="创建项目或等待邀请";含插图+"新建项目"按钮 | 用户无任何项目时 | ⏭ | — | — |
| TC-R21-13 | 视觉 | 空态文案颜色 | color: `--color-text-muted`(#71717a) | 列表为空时 | ⏭ | — | — |
| TC-R21-14 | 视觉 | 页头问候语 | 文案="工作台";font: 19px/600(vp L81) | / | ✅* | BUG-UI-047 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R21-15 | 视觉 | 列表卡片头 | 类别名+"查看全部"链接 | / | ✅ | — | — |
| TC-R21-16 | 视觉 | 列表行结构 | 每行=标题(溢出省略)+项目名(text-muted)+状态徽章+更新时间(相对时间) | / | ✅ | — | — |
| TC-R21-17 | 视觉 | 加载态 | Skeleton 占位 | 页面加载中 | ⏭ | — | — |
| TC-R21-18 | 视觉 | 响应式(≥1280px) | 统计卡片 4 列 | / 视口≥1280px | ✅ | — | — |
| TC-R21-19 | 视觉 | 响应式(≥768px) | 统计卡片 2 列 | / 视口≥768px | ✅ | — | — |
| TC-R21-20 | 视觉 | 响应式(<768px) | 响应式断点 1180px/900px(vp L373/394) | / 视口<768px | ✅* | BUG-UI-049 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R21-21 | 交互 | 统计卡片点击 | 点击卡片整体跳转到对应列表页 | / | ✅ | — | — |
| TC-R21-22 | 交互 | 列表行点击 | 点击行跳转到详情页 | / | ✅ | — | — |

---

## R22 四维管理菜单(需求/任务/测试/发布)

| TC | 类型 | 页面/断言对象 | 断言内容(元素+属性+期望值) | 前置 | 执行结果 | BUG | 截图 |
|---|---|---|---|---|---|---|---|
| TC-R22-01 | 主流程 | /manage/requirements | 需求管理页可达,含页头+筛选栏+Table+分页器 | 已登录 | ✅ | — | — |
| TC-R22-02 | 主流程 | /manage/tasks | 任务管理页可达,四页同构 | 已登录 | ✅ | — | — |
| TC-R22-03 | 主流程 | /manage/tests | 测试管理页可达,含 Table(vp L128-133 .tbl) | 已登录 | ✅* | BUG-UI-050 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R22-04 | 主流程 | /manage/releases | 发布管理页可达,含 Table(vp L128-133 .tbl) | 已登录 | ✅* | BUG-UI-051 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R22-05 | 视觉 | 页面容器 | 含搜索框+筛选栏;vp L1528-1560 有 search input | 四页 | ✅* | BUG-UI-052 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R22-06 | 视觉 | 搜索框 | 含"项目内"/"平台级" tabs(vp L1528) | 四页筛选栏 | ✅* | BUG-UI-053 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R22-07 | 视觉 | Table 表头 | font-size: 12px;font-weight: 600(vp L128: `.tbl th{font-size:12px;font-weight:600}`) | 四页 | ✅* | BUG-UI-054 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R22-08 | 视觉 | Table 单元格 | padding: 10px 16px;font-size: 13px(vp L128-133: `.tbl td{padding:10px 16px;font-size:13px}`) | 四页 | ✅* | BUG-UI-055 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R22-09 | 视觉 | 表格行 hover | hover background: var(--surface-2)(vp L132) | 四页鼠标悬停行 | ✅* | BUG-UI-056 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R22-10 | 视觉 | 分页器 | 居中(vp L235/852/853);margin-top 按 vp | 四页 | ✅* | BUG-UI-057 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R22-11 | 视觉 | 类型徽章-开发 | 文本="开发";样式 primary | /manage/tasks type=dev | ⏭ | — | — |
| TC-R22-12 | 视觉 | 状态徽章-已取消 | 文本="已取消";样式 outline | 四页含 cancelled 数据 | ⏭ | — | — |
| TC-R22-13 | 视觉 | 部署 URL 单元格 | color: #2563eb(--color-accent);可点击新开 tab | /manage/releases | ⏭ | — | — |
| TC-R22-14 | 视觉 | 需求分支单元格 | font-family: mono;宽 180px;溢出省略;复制按钮悬浮 | /manage/requirements | ⏭ | — | — |
| TC-R22-15 | 视觉 | viewer 新建按钮 | role=viewer 时隐藏(不存在) | viewer 角色登录 | ⏭ | — | — |
| TC-R22-16 | 视觉 | 置灰需求下拉行原因文案 | 文本="该需求尚无通过的测试任务(按类型)" | 快速创建对话框前置不满足时 | ⏭ | — | — |
| TC-R22-17 | 视觉 | 空态文案 | padding:40px 20px;text-align:center;color:var(--faint);font-size:13px(vp L338) | 四页无数据时 | ✅* | BUG-UI-058 | — | (期望已按 vp 修正 2026-09-23·二轮) |
| TC-R22-18 | 视觉 | 非成员空态 | 文案="还没有参与任何项目,创建项目或等待邀请" | 非成员用户 | ⏭ | — | — |
| TC-R22-19 | 视觉 | 需求管理特定列 | 优先级(徽章,宽 80px,居中)/ 需求分支(mono 字体,宽 180px,溢出省略,复制按钮悬浮);vp L1661-1708 requirements cols 含"优先级" | /manage/requirements | ✅* | BUG-UI-059 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R22-20 | 视觉 | 任务管理特定列 | 类型(徽章,宽 80px,居中)/ Runner(名称或"—",宽 140px);vp L1661-1708 tasks cols 含"Runner" | /manage/tasks | ✅* | BUG-UI-060 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R22-21 | 视觉 | 测试管理特定列 | 用例通过情况(文本"12/15",宽 110px,居中;全过=success 色,未全过=text-main) | /manage/tests | ⏭ | — | — |
| TC-R22-22 | 视觉 | 发布管理特定列 | 部署 URL(链接 text-accent 可点击新开 tab,宽自适应省略)/ 部署端口(等宽字体,宽 90px,居中) | /manage/releases | ⏭ | — | — |
| TC-R22-23 | 视觉 | 页头结构 | 页标题(text-2xl/600)+右侧"新建 XX"按钮(primary;viewer 隐藏,非成员置灰);vp L1661+ manage 页有 page-head 结构 | 四页 | ✅* | BUG-UI-061 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R22-24 | 视觉 | 筛选栏布局 | flex row + wrap, gap 8px, padding 12px 16px;右侧含统计文案(vp L1695-1700: fbar 右侧有 count text) | 四页 | ✅* | BUG-UI-062 | — | (期望已按 vp 修正 2026-09-23) |
| TC-R22-25 | 交互 | 快速创建对话框 | 宽 560px;项目下拉+按类型表单体+取消/创建按钮;打开关闭正常 | 四页点击"新建" | ⏭ | — | — |
| TC-R22-26 | 交互 | 左侧导航菜单 | 「项目管理」分组下四个二级菜单(需求/任务/测试/发布)切换正常 | 左侧导航 | ✅ | — | — |

---

## 页面清单汇总表

| 页面 | 路由 | 关联需求点 | 用例数 |
|---|---|---|---|
| 登录页 | /login | R1 | 16 |
| 注册页 | /register | R1 | (含在 R1) |
| 找回密码页 | /forgot-password | R1 | (含在 R1) |
| 重置密码页 | /reset-password | R1 | (含在 R1) |
| 个人信息设置页 | /settings/profile | R1 | (含在 R1) |
| GitLab Token 设置页 | /settings/gitlab-token | R1 | (含在 R1) |
| 项目列表页 | /projects | R2 | 10 |
| 项目详情页 | /projects/:projectId | R2, R12, R13, R17 | (含在各 Tab) |
| 需求列表页 | /projects/:projectId/requirements | R3 | 10 |
| 需求详情页 | /requirements/:reqId | R3 | (含在 R3) |
| 任务工作台 | /tasks/:taskId | R4, R5, R9, R10, R11 | 19 |
| 用例审阅页 | /tasks/:taskId/cases | R6 | 8 |
| 测试报告页 | /tasks/:taskId/report | R6 | (含在 R6) |
| 部署状态页 | /tasks/:taskId/deploy | R7 | 5 |
| 成员管理 Tab | /projects/:projectId 成员 Tab | R12 | 7 |
| 模型配置 Tab | /projects/:projectId 模型 Tab | R13 | 9 |
| 归档页 | /requirements/:reqId/archive | R14 | 14 |
| 项目知识库页 | /projects/:projectId/knowledge | R14, R20 | (含在 R14/R20) |
| 平台知识库页 | /knowledge | R14 | (含在 R14) |
| Runner 管理页 | /admin/runners | R16 | 9 |
| MCP 配置 Tab | /projects/:projectId MCP Tab | R17 | 10 |
| Skills 管理 Tab | /projects/:projectId Skills Tab | R17 | (含在 R17) |
| 平台 Skills 市场 | /admin/skills | R17 | (含在 R17) |
| 通知中心页 | /notifications | R18 | 10 |
| 通知设置页 | /settings/notifications | R18 | (含在 R18) |
| 用户管理页 | /admin/users | R19 | 15 |
| 审计日志页 | /admin/audit-logs | R19 | (含在 R19) |
| 知识库列表 Tab | /projects/:projectId/knowledge | R20 | 18 |
| 知识库阅读页 | /projects/:projectId/knowledge-bases/:kbId | R20 | (含在 R20) |
| Dashboard | / | R21 | 22 |
| 需求管理页 | /manage/requirements | R22 | 26 |
| 任务管理页 | /manage/tasks | R22 | (含在 R22) |
| 测试管理页 | /manage/tests | R22 | (含在 R22) |
| 发布管理页 | /manage/releases | R22 | (含在 R22) |
