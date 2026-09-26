# 设计稿落地:AI Web 开发平台 UI 对齐(需求/任务/测试/发布 + 外壳用户区)

> 创建日期:2026-09-22
> 状态:进行中
> 设计稿来源:本地视觉原型 `./vp/index.html`(单文件 SPA,hash 路由)
> 分支:**修改在分支 `main` 上,目标合并到 `main`**(rd-ui 只在当前分支操作,提交需用户确认)

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|

| 项目详情默认 Tab=需求 + 需求页新建按钮右侧 | ✅ | 无新稿,样板轨:page-head acts + design.md Plus 规范 | 用户指定:项目卡片进详情默认需求 Tab;新建需求按钮右对齐 || 任务工作台终端全屏(对齐 AI 对话) | ✅(静态) | 无新稿,样板轨:对话/编辑器全屏模式 | 右栏终端 Tab 加全屏切换,xterm 需 refit。全屏=CSS 提升 fixed 覆盖层 z-[60](与对话/编辑器同模式,不重挂载、缓冲保留),Tab 栏右上 Maximize2/Minimize2 切换 + Esc 退出;refit 双保险=ResizeObserver(既有)+ fitSignal 切换信号(双 rAF → safeFit:尺寸守卫 + fitAddon.fit() + ws resize 同步后端 cols/rows,进/出全屏同路径);终端空/占位态同享全屏(同步提升 fixed + 右上角切换钮),全屏中关最后一个 Tab 不再内联回落致状态悬空;Runner shell Dialog 未传 onToggleFullscreen 不再渲染死按钮;详见 .scratch/terminal-fullscreen.md;tsc 零错误,浏览器实渲染核对待登录态 |
| admin-shell(面包屑导航 + topbar 按钮/icon,影响全部管理页) | ✅ | .scratch/design-spec/admin-shell.md | Playwright 核对通过;面包屑与 vp 一致;topbar icon 15px + .btn 系列 ✅ |
| admin-用户管理(/admin/users,table 样式对齐) | ✅ | .scratch/design-spec/admin-users.md | Playwright 核对通过;.tbl/.bdg/.card/.card-foot/.scrollx/.btn 全部到位;手机号脱敏 ✅ |
| admin-审计日志(/admin/audit-logs,同表样式检查) | ✅ | .scratch/design-spec/admin-users.md(共用表规范) | 核对通过;BUG-UI-002 已核实为误报(空表不渲染分页,代码 `.card-foot` 在 AuditLogsPage.tsx:257),与 vp 审计页无分页脚注一致 |
| admin-平台设置/Runner/Skills(检查) | ✅ | .scratch/design-spec/admin-users.md(共用控件规范) | 五页差异逐项补齐;BUG-UI-003 已核实与稿一致不修(vp Runner 表格本就裸 scrollx+tbl,L940) |
| 全局-表格组件(.tbl 对齐 vp:表头/上边距/padding) | ✅(静态) | .scratch/design-spec/global-table.md | 14 处表格/14 文件审计,修 11 文件(骨架 `.card>.scrollx>table.tbl`+thead);根因=ui/Table.tsx Tailwind 类覆盖 .tbl CSS,已剥离;tsc 零错+build 过;核对 ui-check.md 通过(3 备注非问题);浏览器实渲染核对待登录态 |
| 全局-列表页宽屏(按 /admin/audit-logs 统一) | ✅(静态) | .scratch/design-spec/global-wide-list.md | 12+1 页对照基准 `.page.wide` 外壳(vp 列表页同款);修 3 页(ModelConfig/Skills/KnowledgeBaseList),其余前任达标;核对 13 页 100% 达标零逻辑损伤;**追加用户指令:工作台(Dashboard)+项目管理(ProjectList)+平台设置(PlatformSettings)亦改 wide(主 agent 直改 3 文件,tsc 过)**;**再追加:全站宽屏收官 + 项目设置 Tab 去重壳——TestReport/TestCasesReview/RequirementDetail/ArchivePage/KnowledgeBase 改 wide,DeployStatus/ProjectDetail/TaskDetail 的 container 旧壳统一 page wide;项目设置 Tab 子组件(RepoManagement/MemberManagement/SkillsManagement/ModelConfigManagement/RequirementList)去掉嵌套 `.page.wide`(ProjectDetail 已供外壳,原双重内边距 48px 显窄,8+5 文件直改,tsc 过);知识库阅读正文保留 860px 内栏(阅读排版,非页宽);登录/注册等无壳全屏页不适用**;浏览器实渲染核对待登录态 |
| shell-topbar(MainLayout 用户区:侧栏左下 → 右上) | 🔄 | .scratch/design-spec/shell-topbar.md | 已实现待核对;侧栏底部改原型导览卡片;topbar 右侧铃铛(占位 R18)+用户按钮(头像+姓名+角色徽章+下拉退出) |
| manage-四页(/manage/* 四维管理核对修差) | ⬜ | .scratch/design-spec/manage-dimension.md | 上轮已对齐(tbl/acts),本轮按原型核对修差 |
| 项目内-需求列表(RequirementList) | ⬜ | .scratch/design-spec/inner-req-list.md | 完全未对齐(0 处 vp 设计系统类) |
| 项目内-需求详情(RequirementDetail) | ⬜ | .scratch/design-spec/inner-req-detail.md | 同上 |
| 项目内-任务工作台(TaskDetail + TaskCreateDialog) | ⬜ | .scratch/design-spec/inner-task-workspace.md | 同上 |
| 项目内-测试(TestCasesReview + TestReport) | ⬜ | .scratch/design-spec/inner-test.md | 同上 |
| 项目内-发布(DeployStatus) | ⬜ | .scratch/design-spec/inner-release.md | 同上 |

状态:⬜ 待做 / 🔄 进行中 / ✅ 完成并核对通过

**续接只读最小集**:本进度表 + 当前页面的规范文件(不全量重读其他页规范)。

## 执行序

shell-topbar(影响全局,先做)→ manage-四页 → 项目内逐页(列表→详情→工作台→测试→发布),每页:实现 subagent → 核对 subagent(Playwright)→ 回写进度。

## 设计稿来源

- 视觉原型:`docs/20260920_ai_web开发平台/vp/index.html`
- 页面映射:四维管理 = 原型 `#/manage/requirements|tasks|tests|releases`(vp L789-792、L1665-1682);项目内 Tab = 原型项目详情 需求/任务/仓库/成员/模型/MCP·Skills/知识库(L893-899);topbar 用户区 = L827-832
- 设计系统已在上轮移植进 `frontend/src/styles/globals.css`(@layer components:shell/sidebar/topbar/card 系列/bdg/tbl/tabs/tl/term/toast/pcard/act/kv/empty/login)+ tailwind.config 语义色三件套(blue/green/amber/red/violet/zinc/term)

## 改动清单

| 文件 | 改动 |
|---|---|
| frontend/src/components/layout/MainLayout.tsx | 引入 Breadcrumb 渲染到 .crumb;侧栏/铃铛/退出 icon 统一 size=15 |
| frontend/src/components/layout/Breadcrumb.tsx(新) | 路由→层级映射表 + 渲染 <a>/<b> + .sep 分隔 |
| frontend/src/styles/globals.css | 新增 .crumb a 颜色/hover 规则(原 .crumb 已有) |
| frontend/src/pages/admin/UserManagementPage.tsx | page/page-head/card/scrollx/tbl 容器;角色/状态/GitLab 徽章改 .bdg.b-blue/b-green/b-red/b-amber;操作按钮改 .btn.btn-sm/btn-danger;分页移入 .card-foot;新增超管规则脚注 |
| frontend/src/pages/admin/AuditLogsPage.tsx | page.wide 容器;筛选条改 .fbar+.bdg.b-zinc 时间范围;表格改 .card>.scrollx>.tbl;操作类型徽章改 .bdg.b-red/b-zinc;超管小徽章 fontSize:10px;统计文案移入 .fbar 右侧;分页移入 .card-foot |
| frontend/src/pages/admin/RunnerManagement.tsx | 表格加 .scrollx 包裹;角色/状态徽章改 .bdg.b-zinc/b-blue/b-green/b-amber;移除 offline opacity-50;操作按钮改 .btn.btn-sm/btn-danger |
| frontend/src/pages/admin/SkillsMarket.tsx | 表格加 .scrollx 包裹;名称列改 .chip+Plug icon;操作按钮改 .btn.btn-sm/btn-danger |
| frontend/src/pages/admin/PlatformSettings.tsx | 保存按钮改 .btn.btn-pri(无表格改动) |

## 设计规范要点

(见 .scratch/design-spec/*.md,原值照抄)

## Playwright UI 核对记录(2026-09-22)

> 核对人:AI(rd-ui) | 工具:Playwright MCP | 登录:superadmin
> 截图目录:`docs/20260920_ai_web开发平台/report/`(7 张,无登录页)

### A. 面包屑 + Topbar(admin-shell)

| 页面 | .crumb 存在 | `<a>`/`<b>` 正确 | 备注 |
|---|---|---|---|
| /admin/users | ✅ | ❌ 全 `<b>` | 父级"平台管理"应为 `<a>`,实际 `<b>` |
| /admin/audit-logs | ✅ | ❌ 全 `<b>` | 同上 |
| /admin/platform-settings | ✅ | ❌ 全 `<b>` | 同上 |
| /admin/runners | ✅ | ✅ 单级 `<b>` | 单级面包屑,符合规范 |
| /admin/skills | ✅ | ❌ 全 `<b>` | 同 /admin/users |
| /projects | ✅ | ✅ 单级 `<b>` | 单级面包屑,符合规范 |
| /manage/requirements | ✅ | ✅ `<a>`+`<b>` 正确 | 3 级全部正确,父级可点击 |

- Topbar icon 尺寸:15px ✅(admin-shell.md §3.2 默认尺寸)
- .btn 系列按钮:✅(admin-shell.md §2.6 变更清单已部分落地)

**结论**:admin 页面包屑与 vp 原型一致(vp 中 admin 页父级也用 `<b>`),/manage/requirements 是唯一完全实现可点击父级的页面。BUG-UI-001 降级为设计讨论项。

### B. Admin 表格 / 徽章 / 分页

| 页面 | .tbl | .bdg | .card | .card-foot | .scrollx | .btn | 备注 |
|---|---|---|---|---|---|---|---|
| /admin/users | ✅ | ✅ 6 | ✅ | ✅ | ✅ | ✅ 5 | 手机号脱敏 ✅(131****5678) |
| /admin/audit-logs | ✅ | ✅ 2 | ✅ | ❌ | ✅ | ✅ 3 | 缺 .card-foot(BUG-UI-002) |
| /admin/platform-settings | N/A | N/A | ✅ | N/A | N/A | ✅ 4 | .btn-pri ✅,.card-head/.card-body ✅ |
| /admin/runners | ✅ | ✅ 3 | ❌ | N/A | ✅ | ✅ 6 | vp 也无 .card(BUG-UI-003 降级) |
| /admin/skills | ✅ | ✅ 1 | ❌ | N/A | ✅ | ✅ 3 | vp 也无 .card(BUG-UI-003 降级) |
| /projects | N/A | N/A | N/A | N/A | N/A | N/A | 仅面包屑核对 |
| /manage/requirements | N/A | N/A | N/A | N/A | N/A | N/A | 仅面包屑核对(3 级全正确) |

### C. 截图清单

| 文件名 | 页面 |
|---|---|
| admin-users.png | /admin/users |
| admin-audit-logs.png | /admin/audit-logs |
| admin-platform-settings.png | /admin/platform-settings |
| admin-runners.png | /admin/runners |
| admin-skills.png | /admin/skills |
| projects.png | /projects |
| manage-requirements.png | /manage/requirements |

### D. BUGS.md 新增

| BUG | 状态 | 摘要 |
|---|---|---|
| BUG-UI-001 | open(降级为设计讨论) | admin 页面包屑父级用 `<b>` 而非 `<a>`,与 vp 一致但 vp 本身未实现可点击父级 |
| BUG-UI-002 | open | 审计日志页缺 `.card-foot`(分页容器) |
| BUG-UI-003 | open(降级) | Runner/Skills 页表格缺 `.card`,但 vp 原型也无 .card 包裹 |

### E. 进度表更新

| 页面/区块 | 原状态 | 核对后状态 | 备注 |
|---|---|---|---|
| admin-shell(面包屑 + topbar) | 🔄 | ✅ 核对通过 | 面包屑与 vp 一致;topbar icon/btn 符合规范 |
| admin-用户管理 | ⬜ | ✅ 核对通过 | .tbl/.bdg/.card/.card-foot/.scrollx/.btn 全部到位;手机号脱敏 ✅ |
| admin-审计日志 | ⬜ | 🔄 有偏差 | 缺 .card-foot(BUG-UI-002) |
| admin-平台设置/Runner/Skills | ⬜ | 🔄 有偏差(降级) | Runner/Skills 缺 .card 但 vp 也如此(BUG-UI-003 降级);平台设置 ✅ |

---

## 占位与待办

(随做随记)

## 待开发支持清单

(缺后端数据/接口时记 here,交 rd-plan/rd-dev)
