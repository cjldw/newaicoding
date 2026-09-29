# ISSUES.md — 已验证问题归档

> 项目:ai_web开发平台 | 迁移时间:2026-09-22
> 来源:rd-fix 修复循环(2026-09-22,共 3 轮)| 全部问题已 verified(修复 + 回归实证)
> 回归证据:后端 256/256 pytest 全绿(第 1-2 轮);第 3 轮 BUG-008:260/260 全绿(含 R2.F1 新用例);前端 build 零错误;Playwright 浏览器端到端验证(超管/普通用户双角色)

| BUG | 状态 | 关联需求点 | 类型 | 来源 | 摘要 |
|---|---|---|---|---|---|
| BUG-039 | verified(R19.F5;2026-09-23 真实环境回归:Red 实测 UTC 串 0 条 → Green 69 条;强制 America/New_York 浏览器时区判据 PASS(参数/行数/时间列与 GMT+8 完全一致);重启后新审计事件 created_at 与本地墙钟同刻 = +08:00 固化生效;tsc 0 错 + vite build 过 + 后端 pytest 398/1s/0) | R19.F5(审计日志页;波及 R22 同范式页排查) | 功能缺陷(前端时区错配)+ 用户指令(默认时区钉死 GMT+8) | 用户报告"审计日志没有/接口返回空"(rd-fix 第 17 轮) | AuditLogsPage 时间筛选 toISOString() 发 UTC 串,而 audit_logs.created_at 存本地(UTC+8)裸墙钟,end_time 落后 8h 把全表滤空(复放矩阵:仅 end_time=UTC→total 0,本地串→65)。修复:① 前端显式 Asia/Shanghai formatGmt8 产 GMT+8 裸串(4 处 toISOString 清零)+ 时间列直渲裸串 + isError 分支 + start>end 禁查询;② 用户指令"默认时区东八区":database.py 引擎 init_command SET time_zone='+08:00' 固化 func.now() 写入契约。波及排查:全前端 toISOString 查询参数 0 处其余命中(DimensionPage 展示层 new Date 留观后续轮) |
| BUG-038 | verified(R2.F9;2026-09-23 真实环境回归:重启后 GET /api/admin/platform-settings HTTP 200 + code 0,3 失效键降级为未配置形态 + warning 只记键名,重启后 0 个 500;全量 pytest 333 passed/1 skipped/0 failed) | R2.F9(波及 R23/R24 平台设置、R13 resolve_config 平台回退) | 代码 bug(容错缺失)+ 环境诱因(密钥轮换未重启) | 用户实测 + 后端日志 traceback(rd-fix 第 16 轮) | GET /api/admin/platform-settings 500:platform_settings 表存量密文与当前 PLATFORM_SECRET_KEY 不匹配(09-22 23:03 .env 轮换后长驻 uvicorn 未重启仍用旧密钥写库至 09-23 14:45,全库 5 条存量密文皆失效),`_decode_stored` 逐键解码无容错,单条坏行打挂整个设置页。修复:`_decode_stored` 逐键容错折叠 None + warning(只记键名),消费方经既有 None 语义 2001/13005 干净降级,0 前端改动。运维重录项:platform_settings 3 键(gitlab_webhook_secret/gitlab_bot_token/llm_api_key)+ users.gitlab_token 1 条 + model_configs 2 条(邻接表同根因,范围外) |
| BUG-001 | verified | R19 | 代码 bug | 用户报告 | superadmin 登录后看不到"平台管理"导航分组(后端 schema 丢 role + 前端 user 未恢复) |
| BUG-002 | verified | R19 | 代码 bug(实现遗漏) | rd-fix 分析 | /admin/users、/admin/audit-logs 路由未注册,UserManagementPage/AuditLogsPage 组件缺失 |
| BUG-003 | verified | R19 | 代码 bug(实现遗漏) | rd-fix 分析 | admin 路由无 superadmin 角色守卫,非超管可直达 |
| BUG-004 | verified | R19 | 代码 bug(实现遗漏) | rd-fix 分析 | admin 路由游离在 MainLayout 外壳之外,页面无侧边栏/顶栏 |
| BUG-005 | verified | R1 | 代码 bug(测试基建) | rd-fix 回归发现 | 后端测试套件直连真实 dev 库且 conftest 清理 ~18 张表,跑一次测试即清空开发数据 |
| BUG-006 | verified | R19 | 代码 bug(F2 细节遗漏) | rd-fix 回归发现 | 审计空态文案不符 + 唯一超管"禁用"按钮未置灰 |
| BUG-008 | verified | R2 | 代码 bug(接口契约) | 用户实测 | PUT platform-settings 的 gitlab_bot_group_id 严格 int 校验拒绝数字字符串 → 平台设置无法保存(连带 bot 配置不可用=BUG-009) |
| BUG-UI-001 | verified | R19.F3 | UI 偏差 | 用户指令(重开) | admin 面包屑统一两级且父级可点击 `<a>`,Runner 管理页由单级补为两级(用户设计决策,优先于 vp 原样) |
| BUG-UI-003 | verified | R16.F2 | UI 偏差 | 用户指令(重开) | Runner 表格补 `.card` 包裹,修复 border 与其他管理页不一致(首轮"vp 裸表格"结论系定位偏差,已更正) |
| BUG-UI-004 | verified | R2.F2 | 设计指令 | 用户指令 | 内容区各页大标题统一 vp 页头结构:icon + 标题 + 换行 + 说明(12 页;工作台/项目加 icon 为用户指令,vp 原无;初版误改侧栏已完整回滚) |
| BUG-UI-005 | verified | R2.F3 | 守卫项 | 用户指令 | 项目管理保留右上角新建按钮——核实存在且与 vp 一致;顺带按用户指令删除空态重复按钮(只留右上角) |
| BUG-UI-006 | verified | R19.F4 | UI 偏差 | 用户指令 | 用户管理筛选栏与表格 0.0px 零间距(实测)→ 筛选栏归位卡片内 `.fbar` 条,页头对齐 vp,邀请按钮补 btn-pri |
| BUG-010 | verified | R2.F4 | 代码 bug(前端) | 用户报告 2026-09-22 | 测试连接按钮把 GitLab 侧失败(401)也按成功样式展示(ok 硬编码 true),误导排障方向 |
| BUG-012 | verified | R2.F5 | 代码 bug(接口契约) | 用户报告 + curl 实测 2026-09-22 | GitLab PAT 用 Bearer 头调用全部 401(应 PRIVATE-TOKEN)——test-connection 401 与 BUG-009 建仓无权限的共同根因 |
| BUG-013 | verified | R2.F6 | 代码 bug(接口契约) | 冒烟实测 2026-09-22 | 私有 group 内建 internal 仓库被 GitLab 拒 → 建仓可见性未按组降级 |
| BUG-011 | verified | R17.F1 | 代码 bug(入口断链) | 用户报告 2026-09-22 | MCP/Skills 管理实现齐全但入口断链:项目详情"设置"按钮空 onClick;侧栏无 Skills 市场入口(均已接线,浏览器实测通过) |
| BUG-009 | verified | R2.F5+R2.F6 | 功能/权限(BUG-012/013 连带) | 用户实测 2026-09-22 | 建项目拉取/操作代码无权限——根因除后全链路实证:建仓/clone/push 全通 |
| BUG-014 | verified | R22.F1 | 代码 bug(接口契约) | 用户报告 2026-09-22(运行时崩溃) | 四维管理页 item.key.slice 崩溃:后端返回 req_id/task_id 与前端契约 key 不一致,有数据即白屏 |

> 已接受偏差(不修):R19 分片文件结构中的 `AdminNav.tsx` 未单独建文件,导航项内联在 MainLayout.tsx——行为与规格一致(仅超管渲染)。

### BUG-049 | 项目列表卡片需求数/成员数为硬编码演示数据 | verified(R2.F10)
- **复现**:项目列表卡片需求数恒为「0 个需求」、成员头像写死「罗/王/张」(R1 期演示数据),真实项目有需求有成员也显示错误
- **根因**:后端 `list_projects` 只返回 `repo_count`,从未聚合需求数/成员数;前端卡片为 R1 期硬编码未接真
- **修复记录(2026-09-24,rd-fix 第 16 轮 / R2.F10)**:`list_projects` 批量补 `req_count`(项目全部需求,vp 同口径)与 `member_count`(成员行+owner,R12 虚拟 owner 卡片口径含 owner)——分组查询防 N+1;前端 meta 区绑定 `req_count`、foot 头像栈改 owner 真实头像(getInitial/getAvColor)+「+N」成员角标
- **验证**:pytest `test_list_projects_includes_req_and_member_counts`(直插 2 需求+1 成员行 → req_count=2 / member_count=2)26/26 绿;真机 API 三项目逐项与 DB 实际行数一致(req=1/5/3,members=2/2/3);tsc 零错误
- **状态**:verified

### BUG-064 | /manage/tasks 任务列表查不到打磨任务(type=requirement) | verified(R22.F3)
- **复现**:「开始打磨」创建的打磨任务(type='requirement')不出现在 /manage/tasks;DB 实证 2026-09-28 仅 2 条打磨任务(id 975/977)列表不可见,audit 当日 0 条 task.create(仅 requirement.create/start_polish)——创建链与 scope 过滤链均正常,纯展示口径问题
- **根因**:dashboard_views.py type 白名单仅收 dev/test/release,打磨任务按旧规格被排除(规格口径问题;用户 AskUserQuestion 拍板方案 A=纳入任务列表)
- **修复记录(2026-09-28,rd-fix 第 34 轮 / R22.F3)**:dashboard_views.py 白名单放行 requirement + dev 维混合返回 `Task.type.in_(["dev","requirement"])`;前端零改动(DimensionPage TYPE_BADGE 既有「打磨」徽章映射自动渲染)
- **验证**:新增 pytest 5/5(Red→Green:requirement 行入列表 / dev·test·release 零回归 / scope 不破)+ 触碰面回归 23 passed + tsc 零错(前端零 diff);真机 API:超管 13 条(5 requirement+8 dev)、普通用户仅自有 1 条(scope 不变);无头浏览器复验 3/3 PASS(账号 13900001111 规避超管互踢:登录 → /manage/tasks 打磨行徽章渲染 → 点击行进工作台 /tasks/{id} wb-head 渲染),截图 report/rd-fix-r34/01、02,脚本 .scratch/rd-fix-r34/uiverify.py(首跑点击被 R29 首访导览弹层遮挡,补跳过步骤后全过)
- **分析底稿**:`.scratch/fix-analysis.md` § 第 34 轮;分片 `DEVPLAN/R22.F3.md`
- **状态**:verified(2026-09-28 第 34 轮收敛迁移)

### BUG-053 | 需求创建弹窗分支预览 □ 占位符易误读 | verified(R34.F1 追加域)
- **复现**:创建需求弹窗标题输入汉字,分支预览渲染 `feat/□□□□□20260926`,用户误读为乱码(BUG-DATA-001 归因附带发现 2026-09-26;原登记见 BUGS「R34.F1 移交项」)
- **根因**:R34.F1 初版为客户端 □ 占位设计(注释「汉字以□占位提示,后端权威」),观感差易误读;R34.F1 追加(commit 5c4e4c9)已补后端权威预览——`GET /requirements/branch-preview?title=`(pypinyin 首拼+10 字截断+8 位日期,与 default_req_branch 同口径)+ 前端 useBranchPreview + useDebounce(300ms),唯 BUGS 登记未同步、缺浏览器级证据
- **验证(2026-09-28 第 34 轮追加)**:API 实证「购物车优惠券叠加使用」→ `feat/gwcyhqdjsy20260928`(首拼 10 字截断+8 位日期);浏览器复验 PASS——预览区渲染「分支预览: feat/gwcyhqdjsy20260928(以创建时系统生成为准;可手动改填覆盖)」,无 □,截图 report/rd-fix-r34/03-branch-preview.png(脚本 .scratch/rd-fix-r34/verify053b.py;键盘逐键输入驱动 React 受控组件)
- **状态**:verified(2026-09-28 迁移)

### BUG-068 | 非 owner 成员的项目列表为空(list_projects 只认 owner) | verified(R12.F1)
- **复现**:13900001111(editor 成员,DB 成员行在、项目 5b9ba156 active、dashboard 同口径 GET /api/dashboard/requirements total=1)登录后 GET /api/projects **total=0**、/projects 页空态「还没有项目」——被邀请成员从列表进不了项目(BUG-053 浏览器复验附带发现 2026-09-28)
- **根因**:project_service.list_projects 过滤只按 owner_id,不 join project_members——R12 邀请协作链集成缺口;规格核对:R2.md「成员体系 R12 接入后扩展为成员项目」+ R12.md「数据范围:用户是成员的所有项目」→ 非 owner-only,确认功能缺陷
- **修复记录(2026-09-28,rd-fix 第 34 轮追加 / R12.F1)**:非超管条件改 `owner_id == me OR project_id IN (成员子查询)` 去重;超管口径不变;pytest 5/5 Red→Green(test_bug068_member_list_projects.py,含 owner/成员/软删/超管用例)
- **验证**:API 实证 13900001111 GET /api/projects total=1(原 0);浏览器复验 PASS(/projects 渲染 rd-fix smoke test 卡片「1 仓库/13 个需求/活跃」,截图 report/rd-fix-r34/04-projects-member.png,脚本 verify053b.py)
- **状态**:verified(2026-09-28 迁移);分片留痕:DEVPLAN.md 进度表 R12.F1(无独立分片文件,变更记录留痕,R2.F8 先例)

---

## BUG-001 superadmin 登录后看不到平台设置等超管信息

- **状态**:verified | **修复点**:R19.F1
- **根因(双层缺陷,详见 `.scratch/fix-analysis.md`)**:
  1. 后端 `LoginUserInfo`(schemas/auth.py)与 `UserProfileResponse`(schemas/user.py)未声明 `role` → FastAPI 序列化丢弃 → 前端 `user?.role==='superadmin'` 永远 false
  2. 前端 authStore user 仅存内存,app init 不调 getMe → 刷新后 user=null
- **修复**:后端两 schema 补 role + 构建处传入(auth_service.py / api/users.py);前端 app init hydrate(token 有 user 无 → getMe 恢复,401 登出);UserInfo 类型对齐
- **回归证据**:登录/`/me` 响应含 `role='superadmin'`(curl 实测);浏览器超管登录 → 「平台管理 · 仅超管」分组及 4 子项出现;刷新后仍在;单测 4 条 Red→Green

## BUG-002 用户管理页与审计日志页未实现

- **状态**:verified | **修复点**:R19.F2
- **根因**:R19 决策留痕称前端用户管理/审计页"并入 R21/R22 前端批次",实际该批次未包含
- **修复**:新建 `api/admin.ts`、`pages/admin/UserManagementPage.tsx`(筛选/搜索防抖/列表/分页 20/邀请对话框/禁用确认)、`pages/admin/AuditLogsPage.tsx`(时间范围/操作类型筛选/日志表/详情 Tooltip);router 注册两路由
- **回归证据**:浏览器实渲染——手机号打码 `187****9856`、角色徽章(超级管理员/普通用户)、状态徽章、GitLab 绑定列、注册时间、操作列;审计页 7 列表头齐全;静态核对 ui-check 9 项期望逐行比对通过

## BUG-003 admin 路由无角色守卫

- **状态**:verified | **修复点**:R19.F2
- **修复**:新建 `components/RequireRole.tsx`(等待 hydrate → 校验 role → 不匹配 `<Navigate to="/" />`),包裹全部 `/admin/*` 路由
- **回归证据**:普通用户(13800005678)登录无「平台管理」入口;直达 `/admin/users` 被重定向到 `/`(工作台),两次实测均拦截

## BUG-004 admin 路由游离在应用外壳之外

- **状态**:verified | **修复点**:R19.F2
- **修复**:全部 `/admin/*` 路由(platform-settings/skills/runners/users/audit-logs)移入 MainLayout children
- **回归证据**:超管访问三个管理页均保留侧边栏+顶栏

## BUG-005 测试套件直连真实 dev 库并清空开发数据

- **状态**:verified | **修复点**:R1.F1
- **根因**:`tests/conftest.py` 原注释明确"不覆盖 DATABASE_URL,使用 .env 的 MySQL 开发库",每轮清理 18 张表
- **事故记录**:2026-09-22 R19.F1 修复执行中跑全量测试,dev 库 users/projects/audit_logs 等被清空;账号经正式注册接口恢复(首个注册=superadmin bootstrap),密码统一重置临时值;platform_settings 历史配置如有需用户重配
- **修复**:conftest 强制覆盖 `DATABASE_URL` → 隔离库 `aicoding_test`(同实例)+ 护栏(库名≠aicoding_test 时 `pytest.exit` 拒绝执行)+ 会话级 schema 初始化(alembic,失败回退 create_all 并补建迁移中的 2 个 ngram FULLTEXT 索引——`knowledge_entries`/`knowledge_docs`,修复了 fallback 丢索引导致的 test_search_knowledge 1191 报错)
- **回归证据**:全量 256/256 passed;跑后 `aicoding.users` 仍 2 行(判据 A);故障注入指向 aicoding 被护栏拦截(判据 B)

## BUG-006 用户管理/审计日志两处规格细节不符

- **状态**:verified | **修复点**:R19.F2(补遗)
- **修复**:① 审计空态文案 → "暂无符合条件的日志"(R19 文案清单原文);② UserManagementPage 唯一超管判定(useMemo:当前页可见超管=1 且 total=users.length)"禁用"按钮 disabled + title 提示,跨页局限代码注释说明、服务端 19001 兜底;顺带清理 MainLayout 未使用 import(TS6133)
- **回归证据**:浏览器实测——审计页空态文案精确匹配;超管行 disableBtnDisabled=true + title="最后一个超级管理员不可禁用",普通用户行可点击

## BUG-008 gitlab_bot_group_id 类型校验拒绝数字字符串

- **状态**:verified | **修复点**:R2.F1
- **根因**:后端 `platform_settings_service.py` `validate_setting_value` int 分支 `isinstance(value, int)` 严格拒绝;前端 zod `z.string()` 提交字符串 → "要整形"报错,group_id 无法入库 → `get_gitlab_bot_config` 不完整 → 建仓 403(连带 BUG-009)
- **修复**:后端 int 分支宽容接受可转 int 的数字字符串(strip 后 int() 成功即收,越界/非数字仍拒,存库统一 int);前端保留字符串透传与后端宽容兼容(偏差已留痕 R2.F1)
- **回归证据**:R2.F1 专用用例 4 条(str 接受/带空白接受/"abc" 拒绝/int 接受)落地 `test_platform_settings_api.py`;平台设置段 25/25 ✅;全量 **260/260 passed**(2026-09-22 rd-fix 第 3 轮回归)
- **连带说明**:BUG-009(拉码无权限)为本 bug 连带,代码侧随本修复恢复;其 verified 需用户真实 GitLab 环境重存配置后建仓复验,故仍留 BUGS.md

## BUG-UI-001 admin 面包屑统一两级且父级可点击

- **状态**:verified | **修复点**:R19.F3 | **来源**:用户拍板推翻首轮"与稿一致不修"结论
- **修复**:`Breadcrumb.tsx` EXACT_MAP 5 个 admin 路由统一两级,父级"平台管理"带 `href='/admin/platform-settings'` 渲染为 `<Link>`(可点击),末级保持 `<b>`;渲染逻辑未动(只改映射数据)
- **偏差留痕**:vp 原型 admin 页父级本为 `<b>`(不可点击),本修复为用户设计决策,优先于 vp
- **回归证据(2026-09-22 Playwright 实测)**:/admin/runners crumb = `<a href="/admin/platform-settings">平台管理</a>/<b>Runner 管理</b>`;users/audit-logs/platform-settings/skills 同构;/projects 仍单级 `<b>项目列表</b>`(不受影响)

## BUG-UI-003 Runner 表格缺 .card 包裹(border 不对)

- **状态**:verified | **修复点**:R16.F2 | **来源**:用户指令(重开;首轮"vp 为裸表格"结论经复核系定位偏差,vp L1572 实有 .card)
- **修复**:`RunnerManagement.tsx` 表格 `.scrollx` 外包 `<div className="card">`,对齐 `.card > .scrollx > table.tbl` 统一模式
- **回归证据**:/admin/runners `card>scrollx>table.tbl` 存在,计算样式 border 0.667px / radius 10px,与 /admin/users 卡片一致;数据渲染无回归

## BUG-UI-004 内容区页头统一 icon+标题+换行+说明

- **状态**:verified | **修复点**:R2.F2 | **来源**:用户指令(**解读修正留痕**:初版误读为侧栏菜单加说明行,实施后经用户澄清已完整回滚;正确 scope = 内容区 page-head)
- **修复**:12 页 page-head 统一 `icon + h1 + .sub`——四维页经 DimensionPage 新增 icon/desc props(ManagePages 传 vp conf 原文);runners/users/audit/knowledge 直接改 JSX(sub 逐字抄 vp);工作台/项目加 icon 为用户追加指令(vp 原无,留痕);平台设置/Skills 两页 vp 无原型,文案自拟留痕;/knowledge 全局标题"知识库"→"知识条目"对齐 vp;**侧栏保持单行不变**
- **回归证据**:9 页批量断言 h1Icon=true + subOk=true(vp 原文包含匹配);`sitem .desc` 不存在(回滚确认);tsc 零错误 + build 成功

## BUG-UI-005 项目管理保留右上角新建按钮

- **状态**:verified | **修复点**:R2.F3 | **来源**:用户指令(守卫型)
- **核实**:按钮存在且与 vp 一致(`.page-head > .acts` 内 `btn btn-pri`,Plus +「新建项目」,跳 /projects/create)
- **追加改动(用户第二轮指令)**:删除空态重复的"新建项目"按钮,只保留右上角一个;空态补提示文字「请点击右上角「新建项目」创建第一个项目」
- **回归证据**:/projects 页 `.btn-pri` 全页仅 1 个(右上角);截图 fix-projects.png

## BUG-UI-006 用户管理筛选栏与表格零间距(重叠)

- **状态**:verified | **修复点**:R19.F4 | **来源**:用户指令
- **根因**:筛选栏为游离 Tailwind div(`flex items-center gap-3`),与表格 `.card` 间距实测 **0.0px**;未用 vp 的卡片内筛选条语言
- **修复**:筛选控件(状态 Select + 搜索框)移入 `.card` 内 `.scrollx` 前作为 `.fbar` 条(padding 12px 16px + border-bottom 天生分隔);页头对齐 vp(Users 图标 + 全文 sub);「邀请新用户」btn → btn btn-pri;筛选/搜索/分页逻辑一行未动
- **回归证据**:`fbarInsideCard=true`,fbar padding `12px 16px` + border-bottom `0.667px solid rgb(228,228,231)`;`.card-foot` 分页保留;h1 图标 + 全文 sub;邀请按钮 `btn btn-pri`;截图 fix-admin-users.png

## BUG-010 测试连接结果误标成功(用户所见"401"的真相)

- **状态**:verified | **修复点**:R2.F4 | **来源**:用户报告"接口 /api/admin/platform-settings/test-connection 提示 401,有 token 也 401"
- **接口机制(实测澄清)**:平台接口本身 **HTTP 200 + code=0,鉴权正常**。工作方式 = 取 **DB 已保存**的 gitlab_url + bot_token 调 GitLab `GET /api/v4/version`(gitlab_service.bot_test_connection);200 → ok=true+版本号;非 200 → ok=false + `"GitLab 返回 {status},请检查 token 与地址"`;超时/网络 → "连接失败"。**用户所见 401 = GitLab 对已保存 bot token 返回 401(token 无效/过期/与地址不匹配)经 data.message 透传,不是平台鉴权失败**;且接口测"已保存"配置,表单改了未保存不参与测试(R2 分片既定契约)
- **前端根因**:handleTestConnection 成功分支 `setTestResult({ ok: true, ... })` 硬编码,GitLab 失败也渲染成功样式 → 用户误以为平台鉴权故障
- **修复**:`ok: res.data?.ok === true`,message 保持后端原文;catch(网络/HTTP 错误)分支不动;接口契约零改动
- **回归证据(2026-09-22 实测)**:curl 带 token → HTTP 200 code=0 data.ok=false("GitLab 返回 401…");页面点击「测试连接」→ 失败样式渲染(⚠ 图标 + 401 文案,截图 fix-test-connection.png);tsc 零错误
- **附带发现(未修,留观)**:平台设置页"预览/部署环境基础域名"输入框回显值形如 `VLZ2bamg…`(疑似密文被当明文回显),与本 bug 无关,建议后续单查

## BUG-012 GitLab PAT 鉴权头用错(Bearer → PRIVATE-TOKEN)

- **状态**:verified | **修复点**:R2.F5 | **来源**:用户报告"token 有权限但测试 401"并提供有效 token
- **curl 实证(2026-09-22,gitlab.zhanqirsj.com,GitLab 11.7.0,http-only)**:`PRIVATE-TOKEN: <PAT>` → 200;`Authorization: Bearer <PAT>` → 401;https → 连接失败
- **根因**:`gitlab_service.py` 两处用 Bearer 调 GitLab——`verify_gitlab_token`(R1 个人 token 验证)与 `_bot_headers`(平台 bot 共用头,波及 test-connection/建仓/成员同步/分支全部 bot_*)。GitLab PAT 仅认 PRIVATE-TOKEN,**即 BUG-009(建仓/拉码无权限)的真根因**(group_id 类型只是叠加因素)
- **修复**:两处改 `{"PRIVATE-TOKEN": <token>}`;pytest gitlab 段 18/18 全绿(无存量断言绑定旧头)
- **回归证据(端到端)**:PUT /api/admin/platform-settings 写入用户提供的有效 token → POST test-connection 返回 `ok=true, version="11.7.0", 连接成功`;后端进程(并行会话所起、无 --reload)已同参数重启加载新代码
- **环境遗留(非代码)**:① 平台设置"预览/部署环境基础域名"被误填为 `VLZ2…Zpm7.com`(token 串+域名后缀),需用户改为真实域名;② GitLab 仅 http,无 https(涉 R15 网关/clone 协议)

## BUG-013 私有 group 内建 internal 仓库被拒

- **状态**:verified | **修复点**:R2.F6 | **来源**:BUG-012 修复后的 BUG-009 冒烟复验
- **curl 实证(group 100 = private)**:`POST /api/v4/projects {visibility:"internal"}` → 400 `internal is not allowed in a private group.`
- **修复**:`bot_create_repo` 建仓前 GET `/api/v4/groups/{id}` 读组可见性,请求超出按 GitLab 规则(仓库 ≤ 组)自动降级;读失败不阻断;pytest gitlab+project 段 66/66 全绿
- **回归证据**:冒烟创建项目(visibility=internal)→ code=0,auto 建仓成功(GitLab repo 680 @ group 100,实际落 private)

## BUG-011 MCP/Skills 管理入口断链

- **状态**:verified | **修复点**:R17.F1 | **来源**:用户报告("mcp,skill 的需求怎么没有了")
- **核实**:R17 实现本体齐全(项目设置三子 Tab + /admin/skills + 后端接口),断的是两个入口——项目详情页头菜单「设置」按钮早期占位空 onClick;侧栏无 Skills 项
- **修复**:①「设置」按钮接线 `navigate('?tab=settings')`;② NAV_ADMIN 补「Skills 市场」(Blocks 图标,平台管理组,侧栏保持单行)
- **回归证据(浏览器实测 2026-09-22)**:侧栏 12 项含「Skills 市场」,点击 → /admin/skills 渲染正常(h1 + 新建按钮 + 表格);tsc 零错误;项目设置入口静态核对接线正确

## BUG-009 建项目拉取/操作代码无权限(根因链闭环)

- **状态**:verified | **修复点**:R2.F5(鉴权头)+ R2.F6(可见性降级) | **来源**:用户实测;真根因即 BUG-012/013
- **全链路实证(2026-09-22 冒烟)**:创建项目 `rd-fix smoke test` → code=0,auto 建仓成功(GitLab repo 680 `http://47.111.69.64/pda/rd-fix-smoke-test.git`,平台 repos 绑定 main/auto)→ `git clone` 成功(含初始化 README)→ commit + `git push origin master` 成功
- **备注**:冒烟项目/GitLab 仓库保留给用户查验,可随时删除

## BUG-014 四维管理页 item.key.slice 白屏崩溃

- **状态**:verified | **修复点**:R22.F1 | **来源**:用户报告(应用崩溃栈)
- **根因**:`dashboard_views.py` 需求端点返回 `req_id`、任务端点返回 `task_id`,前端 `DimensionItem` 契约为 `key` → `item.key` 永远 undefined,`key.slice(0, 8)` 崩溃。此前列表恒空未触发,有真实项目/需求数据即白屏
- **修复**:后端两端点 items 补 `"key"` 字段(保留原字段兼容),前端契约零改动
- **回归证据(2026-09-22 实测)**:pytest dashboard 8/8;`GET /dashboard/requirements` items 含 key;浏览器实测 /manage/requirements 渲染 2 行不崩(含用户此前触发崩溃的数据),tasks/tests/releases 三维同验不崩;截图 fix-dimension-page.png

## R25 审计接入·无实现宿主事件口径登记(2026-09-23)

> R25 分片明确:以下 4 项审计事件**无实现宿主/端点,本次不接代码**,登记口径防止后续被当遗漏重报;宿主实现时补接。

| 事件 | 不接原因 | 补接时机 |
|---|---|---|
| auth.logout(登出) | JWT 无状态,无 logout 端点 | 若 V2 增加服务端登出/token 撤销端点 |
| runner.enable(Runner 启用) | Runner API 仅 disable,无 enable 端点(禁用后经 create 重建或直接改库) | 若增加 enable 端点 |
| container.force_push_audit(销毁前强制 push) | 全库未见"销毁前强制 push"实现点(分片 R8 后续项),审计无处挂 | R8 销毁前强制 push 实现时(container_service 留 TODO 已注明) |
| invitation.consume(邀请消费) | `consume_invitation` 函数存在但全库无调用方(注册流程未消费 invitation_token,邀请注册链路未接线) | 注册流程接线 invitation_token 消费时 |

**另留痕(R25 顺带修复)**:`users_admin.py` 原 `_session_factory_holder` 机制无任何注入调用方,致 R19 的 user.disable/enable 审计此前**从不落库**;R25 改为直接引用模块级 `async_session_factory` 修复,并补 pytest 断言。

## rd-fix 第 18 轮迁移(2026-09-24)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-040 | verified(用户浏览器复验待定) | R28.F1 | 个人设置入口断链:头像编辑/GitLab Token/通知设置页面均已实现但 UI 零入口(侧栏无、用户下拉仅退出登录);MainLayout 用户下拉补「个人设置」菜单项(复用 Settings 图标与 .user-menu-item 样式,零新增 CSS) | Playwright 实测:下拉两项 → /settings/profile → 「上传头像」控件在 → 三设置页导航齐;tsc 0 错 + build 过;截图 .scratch/R28.F1/profile-reachable.png |
| BUG-041 | verified | R26.F1 | Runner 终端 6003 对非容器化 runner 误报「版本过旧」:Windows 裸跑无 HOSTNAME→self_container_id 空串,与"旧版镜像无键"折叠同文案;细分 message(键缺失=版本过旧 / 空串=非容器化部署),错误码 6003 不动,0 前端;response.py 枚举注释同步 | pytest 11/11(新增空串用例 Red→Green,既有键缺失用例不回退);真机接口复验(后端重启后):{"code":6003,"message":"该 Runner 未运行在容器中(非容器化部署),无法打开 Runner 终端"} |

## 登记遗留(2026-09-24,rd-fix 第 19 轮)

| 项 | 描述 | 建议归属 |
|---|---|---|
| 任务终态缺容器状态回写 | 任务取消/完成/超时链路不更新 containers.status(滞留 running),产生孤儿容器行——BUG-042 删除 Runner 被卡的直接数据源头(R16.F3 已在删除口径侧兜底) | 后续任务链增强(R4 系修复点或新需求),涉及 cancel/timeout/finish 三条链路 |

## rd-fix 第 21 轮迁移(2026-09-24)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-042 | verified(真机删除实证) | R16.F3 | delete_runner 拦截收窄为容器(creating/running)且关联 Task.status='running'(项目"进行中"统一口径);部署容器 task_id NULL 自然放行;16001 文案改「Runner 上有进行中任务的容器,不可删除」 | pytest 11/11(Red→Green);真机实证:用户于 2026-09-24 14:33-15:00 间成功删除 local-win-test(runners 表行消失,随后旧 token 注册被拒「token 无效」,16001 卡死不复现;证据链见 BUGS.md BUG-044 旁证收获) |

## rd-fix 第 22 轮迁移(2026-09-24)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-045 | verified | R16.F4 | collect_machine_info 内存采集用 `os.sysconf(SC_PAGE_SIZE/SC_PHYS_PAGES)`(仅 Unix 存在),Windows 必 AttributeError 被吞 → mem_total_gb 恒 0;Windows 分支改 `ctypes GlobalMemoryStatusEx`;并按用户指令扩充 os_version/hostname/ip(UDP connect 探默认路由出口,不发包)/disk_total_gb/disk_free_gb/cpu_model,逐字段容错(失败整键缺席,不阻塞注册);前端 RunnerMachineInfo 类型扩 6 可选字段 + formatMachine 两行展示(缺字段降级);后端零改动 | runner pytest 4 新增全绿(实机断言)+ 全量 31/31(与 R31 并行改动互不破坏);tsc 0 错;真机重启 runner 重注册后 DB 实证全字段落库:mem 31.8GB / ip 10.180.106.107 / hostname LUOWEN-CORP / os_version Windows-10-10.0.22621-SP0 / disk 2794.5GB(剩 143.7)/ cpu_model,status=online |

## rd-fix 第 23/24 轮迁移(2026-09-24)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-UI-070 | verified | R9.F2 | xterm 终端无自定义滚动条,深色终端上原生滚动条突兀;globals.css 纯追加 `.xterm-viewport` 样式:WebKit 8px thumb(rgba(255,255,255,.18),4px 圆角,hover .32)+ track 透明,Firefox scrollbar-width thin + scrollbar-color;终端底色恒 #1e1e1e 双主题通用 | 真机浏览器计算样式实证:webkit width=8px / thumb 4px 圆角 rgba(255,255,255,0.18) / Firefox thin——PASS |

## rd-fix 第 25 轮迁移(2026-09-24)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-048 | verified | R31.F2(R31.F1 数据面缺口) | 宿主终端 WS 零输出双层:① 默认命令 `["cmd.exe"]` 缺 `/K`——管道 stdin 下 cmd 非交互模式执行完即退 → stdout EOF → 读循环「宿主 shell 读取结束」永久静默;② xterm Enter 裸 `\r` 不被管道 cmd 认作行尾(真实 pty 的行尾仿真在管道模式缺失)。修复(runner 侧,容器 pty 零改动):默认命令 `["cmd.exe","/K"]` + `write_input` 宿主分支 `\r\n→\n→\r→\n→\r\n` 幂等归一 | runner 35/35(含新增存活回归门 test_host_shell_alive_after_spawn);真机 E2E:R31 重启载新代码 → ?force=true 清场(复验 BUG-047)→ 裸 WS 以与 xterm Enter 一致的裸 \r 收到完整回路「提示符→echo 执行→输出→新提示符」;探针 `.scratch/rd25_ws_probe.py` |

## rd-fix 第 26 轮迁移(2026-09-24)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-049 | verified(需求修正) | R31.F3 | 用户推翻 R31 Q51 负向规格:本机快速创建=平台直接以 Docker 容器运行 runner(零命令复制)。spawn_local 重写:镜像缺失自动构建(Dockerfile ARG BASE_IMAGE 参数化;docker.io 不可达时自动回退本地 python:3.10——实测 registry-1.docker.io 直连超时,pypi 可达)+ docker run 挂载 docker.sock/env 四键/host.docker.internal 回连/--restart unless-stopped;容器名确定性推出(qicheng-runner-<id8>,平台重启凭名可停);删除链路补容器 remove;exec 消息 cwd=/app 适配(Runner 容器 WORKDIR,任务终端 /workspace/main 默认不变);子进程形态废弃保留存量兼容 | 后端 51/51(r31/runner_admin/r26_shell,端点测试 mock 在服务边界零破坏);runner 36/36;真机:首建 145s(自动构建)→ qicheng-runner 容器 Up → runner online → machine_info=容器视角且 self_container_id=容器短 id → R26 终端真 pty 回路 PASS(root@…:/app# echo 实证) |
| BUG-050 | verified | R26.F3(波及 R9;一切 Linux 容器形态 runner) | `_read_loop` 硬编码 `session.sock.recv(4096)`——docker exec_start(socket=True) 在标准 Linux/Docker Desktop 返回 SocketIO(file-like 只有 .read()),AttributeError 秒崩零输出;Windows NpipeSocket 有 recv 故历史未暴露(R26 判据 4/8/11「真实 pty 待测」之债)。修复:探测式读法(recv 有则用否则 read,与 BUG-031 写侧探测同思路) | runner 36/36(新增 test_read_loop_supports_socketio);真机容器终端回路 PASS(与 BUG-049 同轮实证) |

## 登记遗留(2026-09-24,rd-fix 第 20 轮)

| 项 | 描述 | 建议归属 |
|---|---|---|
| BUG-044(R31 并行会话工作区,未代修) | test_r31_local_runner 10 failed/2 errors:① delete local 链路把 AsyncMock/未序列化对象写入 audit_log.detail(JSON 序列化炸,PendingRollbackError 实证);② conftest 的 alembic upgrade 失败(fallback create_all,疑 R31 迁移记账漂移);③ runners.py 曾出现装饰器与注释粘行致 reset-token 404(本轮已修,疑两会话编辑碰撞) | R31 并行会话收口时处理 |

## rd-fix 第 20 轮迁移(2026-09-24)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-043 | verified | R31.F1 | 非容器 runner 无终端通道(R26 终端=exec 进自身容器;R31 本机裸跑 runner 成一级能力后缺口凸显)。宿主 shell 降级通道:terminal_manager.py HostSession(subprocess,Windows=cmd.exe/Linux=bash,read1 防凑满阻塞)+ main.py exec "__host__" 哨兵分流 + runners.py 空串分支建 host 会话(键缺失仍 6003);审计 session_kind=runner_host;前端零改动 | runner 单测 6/6(真进程 echo/stdin/kill);后端 r26 11/11 + 触碰面 47 绿;真机:reset-token→新 token 重拉 runner-local→shell-sessions code=0(会话已关)。Windows 管道模式无 pty(resize/真 TTY 降级)接受 |

## rd-fix 第 27 轮迁移(2026-09-25)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-UI-071 | verified | R14.F1(波及 R29 导览) | GET /api/requirements/{id}/archive 恒 500:knowledge.py:31 遗留无效 import(get_requirement_or_404 实际在 requirement_service,下一行已正确导入),每请求必 ImportError。修复:删该行(一行,其余零改动);前端 useTourSteps 四查询加 enabled 门(导览开 && 前置数据就绪才发链式请求,未开零请求;TourDialog 增 open prop) | Red 2/2 实录 ImportError→Green 2/2;触碰面 21/21 两轮(bug071+knowledge+kb+requirements+files);真机重启(2905→10750)archive 存在=200 code=0/不存在=404,主会话独立登录复放同结果;tsc 0 错+build 过;浏览器走查归 rd-test |
| BUG-UI-072 | verified | R28.F2 | 超管 18767169856 avatar_url+avatar_file_path 两列均指向已丢失文件(R19 数据事故遗留)→每页 404。修复:① 数据侧两列置 NULL(.scratch/R28.F2/clear_avatar.py,断言 dev 库 120.27.217.194/aicoding,只动该行);② 前端 utils/avatar.ts 模块级 failedAvatarUrls Set,Avatar/MainLayout 顶栏/ProfileSettings 三消费点命中即首字母回退零请求 | DB 读回断言 NULL;三消费点 grep 断言落位;tsc 0 错+build 过;test_r28_avatar(+upload)批内绿(55 passed);浏览器 network 无 404 复核归 rd-test/用户一瞥 |
| BUG-UI-073 | verified | R19.F6 | /admin/audit-logs 详情列宽不足,「JSON 摘要」断词两行。修复:TableCell whitespace-nowrap + colgroup 详情列 90→110,文案不变 | grep 断言落位;tsc 0 错+build 过;视觉复核归 rd-test/用户一瞥 |

## rd-fix 第 28 轮迁移(2026-09-25)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-UI-074 | fixed(视觉复核归用户) | R4 任务工作台(393c86c 五批整改遗留) | 任务详情页边距重叠/溢出:① .wb 高度魔法数 calc(100vh-108px) 源自 459603a,393c86c 新增 stps-band(~83px)未同步 → 工作台下溢 ~90px,tree-foot/card-foot 出视口+双滚动条;② .page 22/24 padding 与 wb-head 10/16、stps-band 12/16 三重 gutter 无统一对齐线;③ stepper 包整页唯一浮卡与拼贴分栏风格打架,wb-head 底线+卡顶线双重 1px;④ wb 三栏无外框贴页缘毛边;⑤ wb-head 单行 flex-wrap 换行悬挂;⑥ 左 sash right:-3px 被 col-tree overflow:hidden 裁 3px,左右热区不对称;⑦ pendingCenter 独用带框卡与四分支 twrap-fill 语言不一;⑧ 栏内 gutter 10/12/16 五种并存。修复(globals.css wb 区+TaskDetail):页根 .page-fill 零 padding,.main 补 min-height:100dvh 建立 flex 链,.wb 删 calc 改 min-height:600px+margin:0 16px 16px+圆角外框 overflow:hidden;sash 7px 全内探;stepper 去卡并入头带(.stps-band 白带+底线,.stps-card 基类保留零消费者);wb-head 拆两行(.wb-head-main/.wb-head-sub);tabs/d-chips/tree-foot 横向 gutter 统一 16,d-chips 灰底次级化;.rpane 三 pane 统一 12px 空气垫(去 pad-12);pendingCenter 改 twrap-fill;清死代码(.stp.cur 无消费者规则组/重复 [hidden] 块);.stp min-width 86→72;≤1180px .wb min-height:0 解高度锁+col-right min-height:420 | tsc 0 错;grep 断言 stps-card/pad-12/stp.cur 零引用;视觉复核(1440/1920、四任务类型、pending、≤1180、暗色)归用户一瞥 |
| BUG-UI-076 | fixed(视觉复核归用户) | BUG-UI-074 复核反馈 | 用户复核「边线都重叠了」,两类:① 接缝 1px 线双重——A4 外框 overflow:hidden 虽裁顶/底/左/右缘,但三条内部横缝残留:wb-head-main 底线 × stps-band 内 stepper 上边距、右栏 .tabs 底线 × rpane 12px 空气垫内 chat/activity 内卡(Tailwind border-border)顶线、中栏 .tabs 底线 × 各 pane 顶缘;② A0 高度副作用:仅加 min-height:100dvh 时内容仍把 flex 链撑过视口(.wb 600+头带~150+margin 16>100dvh),工作台底部外框线仍出视口。修复:.main 改 height:100dvh+overflow:hidden(flex 链硬钳位,页级滚动由栏内 scroll 承接);.wb .tabs margin-bottom:-1px 吃掉 pane 顶线(豁免编辑器 h1 边线同色无缝);.col-tree .tree-scroll margin-top:-1px 吃掉外框顶线。未动:嵌入子页(TestCasesReview/TestReport/DeployStatus)的 .card/Card 内卡边框与统计卡 mb-6——半页内容保留卡片语言属设计口径,非重叠 | tsc 0 错+build 过;视觉复核归用户一瞥 |
| BUG-UI-077 | fixed(视觉复核归用户) | BUG-UI-076 复核反馈 | 用户复核「保持状态轴,页面 border 不要重叠」:① stepper(状态轴)保留在头带不动;② 补 BUG-UI-076 漏网贴边线:stps-band 底线与 wb 外框顶线间隔 0 直接双线(撤 stps-band 底线,状态轴带与外框顶缘自然衔接);三个嵌入子页(用例/测试报告/部署日志)卡片贴 tabs 底线与栏左右缘(embedded 根加 .emb-pad{padding:12px 16px 16px} 空气垫,卡片不再撞线);撤 BUG-UI-076 的 tree-scroll margin-top:-1px(外框顶线已由 stps-band 衔接,该 hack 反成树节点顶撞线) | tsc 0 错+build 过;视觉复核归用户一瞥 |
| BUG-UI-078 | fixed(视觉复核归用户) | 需求详情页(rd-ui 走查) | requirements/:id「关联任务」标题文字贴卡片左边线:该卡用 vp .card 基类(L266 无内边距,padding 由消费方提供),但漏加卡壳内边距,同页「基本信息」卡有 p-6 故正常。修复:卡片补 p-6,顺带补 mb-6 与基本信息卡对齐(原卡底距缺失贴页底) | tsc 0 错;视觉复核归用户一瞥 |
| BUG-UI-079 | fixed(视觉复核归用户) | BUG-UI-078 复核反馈 | 用户复核「表头和已有页面(manage/releases)不一致」:① 根因——BUG-UI-078 整卡 p-6 把 .tbl th 灰底(var(--surface-2),globals.css:282)也内缩 24px,而 DimensionPage(manage/* 共用)表格贴卡缘渲染、灰底贯通整宽;② 修复为「标题区 p-6 pb-0 内边距 + 表格区贴卡缘」,灰底贯通,操作列改 th/td.ops 右对齐(DimensionPage 口径),查看按钮 ghost Button 换 vp .btn.btn-sm,行加 rowclick 整行可点跳任务页(按钮 stopPropagation 防双跳);③ 顺带核查:Table.tsx 组件零样式全交 .tbl CSS,此前表头「不一致」主因即 p-6 内缩,非 token 漂移 | tsc 0 错+build 过;视觉复核归用户一瞥 |
| BUG-UI-080 | fixed(视觉复核归用户) | 用户口径(撤销 BUG-UI-074 状态轴) | 用户口径「任务页面不要 创建/打磨/评审/已评审/开发/测试/发布 状态栏」:整段移除任务页流程 stepper——JSX stps-band 块、FLOW_STEPS/mapStep/curStep 全删(grep 断言全站零其它消费者),.stps-band 容器类与 .stps/.stp.on 规则组同步清除(此前步已删 .stp.cur 死规则),.stepper/.stp 基类保留属 vp 原型体系;wb-head 头带直接与 .wb 工作台外框衔接,头带底缘与外框顶缘间隔 0 无线重叠(沿用 BUG-UI-077 口径) | tsc 0 错+build 过;视觉复核归用户一瞥 |
| BUG-UI-081 | fixed(视觉复核归用户) | 用户口径(任务页分栏按角色调整) | 用户口径「requirement(需求打磨)任务面向产品、着重对话;dev 等面向开发者保持现状」:① requirement 类型任务左右栏对调(swapPanes)——对话/终端/活动 面板从右栏 384px 移到中栏占 1fr 主工作区,PRD 草稿/工作区 面板移到右栏 384px;dev/test/release 三类型保持 中=工作区/右=对话 不变;② 实现:rightPane 提为与 center 平级 JSX 变量,渲染处按 swapPanes 互换,hidden 保活/全屏/导出能力零改动;③ 停止按钮位置核查:acts 已在 wb-head 主行 margin-left:auto 右侧(BUG-UI-074 拆行后天然满足),零改动;.wb 补 min-width:0 防对调后内容挤压溢出 | tsc 0 错+build 过;视觉复核(打磨/开发两类型对照)归用户一瞥 |
| BUG-UI-082 | fixed(视觉复核归用户) | BUG-UI-081 复核反馈(打磨任务头带) | 用户复核「打磨任务 wb-head-main/sub 样式乱,停止按钮要同其它页面一样放最右」:根因——主行 flex-wrap:wrap,打磨任务标题(类型徽章+短id+标题+运行中徽章)较长时 acts(停止任务)被挤换行,落到次行左缘与 chip-row 混排;且 .ttl 无收缩约束、truncate 类未定义(Tailwind v3 无该类,纯装饰)长文不省略。修复:.wb-head 改 flex-direction:column 两行独立;主行 flex-wrap:nowrap + .ttl flex:1+overflow:hidden + .ttl .truncate 定义(省略生效) + .acts flex:none 恒贴最右;次行 chip-row 保留 wrap。所有任务类型头带布局统一 | build 过(纯 CSS);视觉复核归用户一瞥 |

**留痕(第 28 轮未动项)**:① 右栏三组件内卡语言分裂(chat/activity Tailwind 内卡 vs 终端 #1e1e1e 硬编码 vs 编辑器零边框)与 R30 暗色 token 核对单独立项;② --color-* shadcn 双轨 token 未合并;③ 全屏覆盖层 Tailwind p-2 与 px 尺度不同源。

## R32 任务对话 Skills/MCP + 流式输出(2026-09-25,需求确认后实施)

| 项 | 状态 | 说明 |
|---|---|---|
| R32.F1 容器注入 | fixed(真机复核归用户) | 用户口径「任务对话像 claude 终端一样用 skills/mcp」:容器就绪(handle_container_started)后 inject_task_claude_assets 经 exec_tool=claude_inject 下发——项目已装 Skills 写 /root/.claude/skills/{name}.md(名称安全字符过滤防路径穿越),MCP 配置合并写 /root/.claude.json 的 mcpServers 段(既有键保留);Runner 侧线程池执行防堵事件循环;无资产零下发,注入失败降级不阻塞容器就绪。全任务类型生效(claude CLI 进程级读取,对话/终端同享) |
| R32.F2 / 补全 | fixed(真机复核归用户) | TaskChat 输入框 / 触发项目已装 Skills 下拉(沿用 @ 文件补全模式,互斥),选中插入 @skill名(claude CLI 原生 skill 引用);数据源 GET /projects/:id/skills 现成接口;TaskDetail 传 projectId |
| R32.F3 流式输出 | fixed(真机复核归用户) | 对话从「转圈等结果(最长 600s)」改逐字流式:容器内 claude -p --output-format stream-json --verbose(socket 按行读,BUG-050 探测式 recv/read)→ Runner claude_stream 行事件上泵(复用 _MAIN_LOOP/_SEND_LOCK 线程泵)→ 平台 runner_service 流式注册表(req_id→queue;result 先结算流式请求)→ task_service.send_message_stream 边迭代边经任务事件 WS 广播 chat_delta → 前端 useTaskChatStream 订阅,发送中 AI 气泡逐字增量+光标,chat_done/消息落库后消失;POST /messages 接口与返回不变,旧非流式链路(run_prompt/claude_prompt)保留未被调用 |

验证:后端 pytest test_r32_chat_stream_inject 5/5(注入下发/零下发/stream 事件转换/流式生命周期);runner pytest test_r32_claude_stream 5/5(注入合并/逐行上泵/非 JSON 兜底/session flags),runner 全量 45/46(1 failed=test_host_shell_alive_after_spawn Windows 专属回归,本机 Darwin 未标记 skip 属存量,git status 断言该文件零改动,与 R32 无关);前端 tsc 0 错+build 过。**真机复核归用户**:① 项目装 Skill 后新任务容器 ls /root/.claude/skills;② 对话发消息看逐字流式;③ / 补全下拉。

## R33 侧栏抽屉 + 导览弹窗优化(2026-09-26,rd-ui)

| 项 | 状态 | 说明 |
|---|---|---|
| R33.F1 侧栏抽屉 | fixed(视觉复核归用户) | 用户口径「左侧菜单支持抽屉收起打开」:顶栏面包屑左加 PanelLeft 开关,220px ↔ 56px 图标栏(.shell.side-collapsed 栅格列切换);收起态隐藏 logo 文字/sgroup/lbl/cnt/tour 卡,图标居中,title 原生 tooltip;localStorage(sidebar_collapsed)记忆;≤900px 断点侧栏已横向化,收起态天然不生效(无冲突) |
| R33.F2 导览弹窗优化 | fixed(视觉复核归用户) | 标题补 Play 图标 + 副标语(「按顺序走一遍…约 2 分钟」);步骤行升级:序号圈放大 15→20px 灰底、hover 主色填充,标题 13px 主色加 hover 边框,右侧 ChevronRight 箭头 hover 淡入;旧 L489-491 规则保留,新规则同特异性靠后覆盖 |
| R33.F3 对话泡泡不可读 + 工作台对齐 | fixed(视觉复核归用户) | 用户复核「对话泡泡底色和文字都是黑色看不清」:根因双层——① TaskChat 气泡用 Tailwind bg-muted/text-foreground/text-primary-foreground,但 tailwind.config.ts 从未映射这些 token → 落 Tailwind 默认色板(亮灰 bg + 近黑文字,主题恒定);② 用户「没有改变」实证:dev server(vite)HMR 下 Tailwind 工具类不随 config 重组装,config 映射补丁不可靠。根治:气泡改专用类 .chat-bubble-user/.chat-bubble-ai,直接挂 vp token(--primary/--color-primary-fg/--surface-2/--text,暗色 user 泡反色 #0d1117 与 .btn--primary 口径一致),globals.css 直服零组装依赖;tailwind.config.ts 的 token 映射保留(修正根基,build 产物已断言 var(--surface-2) 生效)。顺带:右栏(操作区)顶部 -1px 补位与左树 tree-tabs/中栏 tabs 顶对齐 + 底部外框兜住满屏;左树 tree-foot 与中栏 card-foot 底缘对齐核查(col-tree flex 列 tree-scroll flex:1 已撑满贴外框底线,代码层无落差,残留偏差归视觉复核) |
| R33.F4 三栏 title 底线 1px 差 | fixed(视觉复核归用户) | 用户复核「左树-中栏-右栏 title 底部 border 差 1px」:根因——左树 FileTree tab 条是裸 Tailwind(flex border-b,行高由 py-2+text-sm 自然撑 ~35.5px),中/右栏 .tabs 是 vp 体系(tab padding 8px 13px ~34.5px),两套行高亚像素差 + 上轮 .col-right margin-top:-1px 把右栏再错 1px。修复:三栏 title 条统一 34px 等高(.wb .tabs{height:34px;flex:none};左树新增 .ft-tabs/.ft-tab 专用类 33+1 结构,margin-bottom:-1px 吃外框顶线与 .tabs 同手法),FileTree 裸 Tailwind 类全替换;撤 .col-right margin-top:-1px hack(等高后自然对齐) |
| R33.F5 工作台高度未铺满 | fixed(视觉复核归用户) | 用户复核「高度只占屏幕一半」:根因——R2.F3 引入的 .route-scroll 滚动口(MainLayout 包 Outlet)只有 overflow-y:auto,不是 flex 容器,.page-fill 的 flex:1 相对 auto 高度父级无效 → 工作台只撑内容高。修复:.route-scroll 改 flex 列 + 直接子级 flex:1 0 auto(普通页自然高度可滚动不受影响)+ .route-scroll>.page-fill{flex:1 1 auto}(满屏页占满全高);min-height:600px 兜底保留,矮窗(780px)下滚动口自然滚 |
| R33.F6 需求归档页样式未统一 | fixed(视觉复核归用户) | 用户复核「/requirements/:id/archive 没按网站统一实现」:根因——ArchivePage 是 shadcn Card + Tailwind 手绘混排(container 加载态/手绘时间线/pre 裸样式/.card 裸卡标题贴边表格内缩),与全站 vp 卡片语言脱节(此前 BUG-UI-078/079 同款病灶)。修复:全页迁移 vp 体系——加载/空态走 .page-loading;页头与需求详情同构(返回 ghost + h1 icon + 状态徽章 + 创建人/时间);时间线 Tailwind 手绘版换 .timeline/.tl-item 现成体系(done 态主色圆点 + Check + when mono 时间);卡片统一 .card/.card-head/.card-body;总结 pre 补 .md-pre 浅底 mono 块(与 md-code 深底终端块区分);知识表贴卡缘灰底贯通 + 操作列 ops 右对齐 + rowclick 整行可点 + .btn.btn-sm(BUG-UI-079 口径) |
| R33.F7 面包屑修复 | fixed(视觉复核归用户) | 用户口径「页面面包屑也修复下」:① 归档页 pattern 链补全(原 需求详情/归档 两级断链 → 项目管理/需求/归档 三级,与需求详情同构);② ArchivePage 挂 BreadcrumbOverrideProvider(项目管理/{需求标题}/归档;RequirementDetail 类型无 project_id 字段,项目名层级留待后端补字段后升级——待开发支持清单);③ 顺带清除全站残留 container mx-auto 加载/空态壳 4 处(RequirementDetail×2/TestReport/TestCasesReview,统一 .page wide + .page-loading) |
| R33.F8 成员管理样式统一 | fixed(视觉复核归用户) | 用户口径「项目详情成员管理 dialog 按网站已有风格」:① 成员表操作列 ghost 按钮串(视觉过弱、移除仅红字)改 ops 右对齐 + .btn.btn-sm,移除升级 .btn-danger(与 BUG-UI-079 表格口径一致);② 空态补 .empty;③ 四个弹窗(邀请/改角色/移除/转让)表单 Tailwind space-y 组合改 .dlg-form+.field(gap 14px 统一节奏,与 Dialog p-6 壳同体系);④ Dialog 基件核查:遮罩/圆角/shadow/动画与全站其它弹窗同源无需动 |
| R33.F9 弹窗底栏按钮统一 | fixed(视觉复核归用户) | 用户复核「邀请 dialog 取消/确认按钮没改好」:根因——DialogFooter 基件用 shadcn 原类 flex-col-reverse sm:flex-row sm:space-x-2,移动端纵排叠加(取消/确认上下叠),且 space-x 依赖旧版 Tailwind 间距插件(该工程 v3 无此 token)按钮间无间距。修复:DialogFooter 基件类改 .dlg-foot(横排右对齐 gap 12 上间距 16,与 tour-dialog-foot 同构)——基件层修复,全站所有弹窗(邀请/改角色/移除/转让/驳回/创建任务/Profile 等 DialogFooter 消费点)一次到位 |
| R34.F1 需求分支默认策略更换 | fixed(真机复核归用户) | 用户口径「默认 req- 更换成 feat/{需求名简称首拼≤10}{日期}」:① 后端 requirement_service 新增 gen_req_branch_slug(汉字拼音首字母 pypinyin FIRST_LETTER + ASCII 词首字母,截 10,空回退 req)+ default_req_branch(feat/{slug}{Asia/Shanghai YYYYMMDD},与平台 +08:00 固化口径一致),create_requirement 未填分支走新策略,显式填写优先不变;② 同日同首拼撞名:自动生成追加 req_id 短码脱撞,显式填写维持 400 报错;③ 依赖:pypinyin>=0.50 入 pyproject(本机 uv 经清华镜像装 0.55.0——pypi.org 直连 TLS 失败,部署机同需镜像或代理);④ 前端 RequirementList 预览同步 feat/ 策略(汉字以 □ 占位 + 「以创建时系统生成为准」提示,后端权威)。验证:pytest test_r34_req_branch 13 例 + 存量 test_requirements_api 9 例全绿(其中 1 例断言 req- 前缀已按新口径更新);tsc 0 错 |
| R35 流程断点修复包 | fixed(真机复核归用户) | 用户反馈「打磨任务取消后没有再开启的地方」rd-prd 流程分析实证 6 断点后开发:F1 打磨可重启(start_polish 放宽:polishing+关联 task 终态→清空 polish_task_id 重建,active 仍 3001;build_detail 透传 polish_task_status 前端免二次请求);F2 取消需求收尾(polish task 未终态→finish_task(cancelled)+容器销毁,失败降级告警不阻塞);F3 retry 拉起(failed/cancelled/timeout→pending→start_task 立即拉起,无 Runner 回 pending;前端 TaskDetail 三态补「重试」按钮激活 useRetryTask 死代码);F4 in_progress 死 UI(前端「创建测试/发布任务」改挂 approved+任务态,后端 _TYPE_REQ_STATUS 本就允许);F5 sweep_timeouts 挂 main.py 调度(60s 轮,死代码激活);F6 running test/release 停止按钮(acts 覆盖改追加)。验证:pytest test_r35_flow_fixes 16/16(含 draft 回归/撞名脱撞/失败降级/非终态拒绝);前端 tsc 0 错+build 过。留痕:测试环境 MySQL 锁竞争期间并发会话跑同库造成 1205/1213 抖动,清理连接后全绿;RunnerManagement openEdit/TagValue 与 projects.ts variables 三处 TS6133/6196 顺手清理(其它会话引入,构建门禁) |

**未代修留痕(第 27 轮越界发现)**:① 测试隔离——test_terminal_api 单跑 8/8 绿,紧跟 avatar/r8f4 等文件同会话跑则 9 errors(sqlalchemy 会话状态跨文件泄漏;全量轮 21E 同类+并行会话同库死锁叠加),非产品缺陷,测试基建待办;② 本机 docker SDK 未装(用户口径「docker 本机不装,保证代码 ok」),test_r31_local_runner 4 例 ModuleNotFoundError 属预期环境约束,R31 本机快速创建在本机不可用,部署机启用时需装 docker SDK 并补 pyproject 声明(本轮曾装 7.2.0 已按口径卸回)。

## rd-fix 第 28 轮迁移(2026-09-26)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-051 | verified | R21.F1(工作台门槛;波及 M1 只读) | 前端 Dashboard.tsx `hasProject` 用 owner-only /api/projects(project_service.py:326-331 owner 条件)判「有无项目」,而 summary 数据口径=成员可见(dashboard.py:26-43)→ 非 owner 成员整统计区被「还没有项目」空态顶掉,统计「看似不对」;数字本身(created_by=me,R21 Q21)与 DB 对账一致非 bug。修复:summary 增 `visible_projects=len(pids)`(dashboard.py:73 一处);前端门槛改 `(summary?.visible_projects ?? 0)>0` 并移除 owner-only useProjectList;统计口径不动(项目维度口径变更诉求归 /rd-plan) | Red 2 用例 KeyError('visible_projects')→Green;test_dashboard.py 10/10(8 既有零回退);tsc 0 错+build 过;真机测试账号(非 owner 成员)summary visible_projects=1(热加载未重启),主会话独立登录复放一致;浏览器工作台渲染统计卡归 rd-test/用户一瞥。**附注**:用户对比的 8 条 dev 系超管创建,按规格不计入测试账号卡片,属口径歧义非缺陷 |

## rd-fix 数据修复迁移(2026-09-26,BUG-DATA-001)

| BUG | 状态 | 关联 | 根因与处置 | 验证 |
|---|---|---|---|---|
| BUG-DATA-001 | verified(2026-09-26 数据修复;open 当日登记当日清理) | —(测试脏数据,非代码 bug;零代码改动) | tasks 表 id 945/946 标题 `??????`/`??????2`(HEX=`3F3F…` 字面 ASCII 问号字节,非 mojibake):2026-09-23 rd-fix 第 8 轮本地 Runner E2E 时外部测试客户端(Windows 控制台 GBK 代码页)在创建请求 payload 侧把中文打成 `?` 写入的测试脏数据,两任务均 cancelled(归因证据:同窗口 id 947 中文完好/同行 error_message 后写中文完好/charset 全链路 utf8mb4);拼音/分支命名代码无产生 `?` 路径(pypinyin errors='ignore' 跳过不替换)。处置=就地改名保留留痕(禁删行):SELECT 确认仍乱码后 `UPDATE tasks SET title='历史测试数据(已清理)' WHERE id IN (945,946) AND title IN ('??????','??????2')`(带前置守卫),rows affected=2、其余行零触碰、未 DELETE。归因附带发现两缺口已登记 BUG-052/BUG-053(open,移交并发会话 R34.F1) | 复检 SELECT:两行 title HEX=`E58E86…`(「历史测试数据(已清理)」合法 UTF-8);全库扫尾 `tasks.title LIKE '%?%'` 其余 0 条 + `requirements.title/req_branch LIKE '%?%'` 0 条,乱码清零。分析 `.scratch/pinyin-analysis.md`,结论 `.scratch/pinyin-fix.md` |

## rd-fix 第 29 轮迁移(2026-09-27,BUG-054/055/056;用户三项复验通过)

| BUG | 状态 | 关联 | 根因与处置 | 验证 |
|---|---|---|---|---|
| BUG-054 | verified | R32.F4(R32 增量6) | 并行会话提交时 runner_service.py 被回退到 HEAD,R32 四处改动(validate_tags/ALLOWED_TASK_TAGS/update_runner/pick_runner_db task_tag 形参)丢失而调用方(container_service:99/task_service:402/api runners)均存活已入库——断链致打磨(500)/start_task/PATCH 编辑/创建 tags 全链 TypeError。修复=原样恢复四处改动 | 一手证据 backend 日志 TypeError;R32 套件 21/21 绿;真机:打磨「调整」返 200 拉起任务;用户复验通过 |
| BUG-055 | verified | R8.F5(容器对账;runner+后端) | container_started 回报在平台事件循环停滞窗口丢失(00:30:08-28,双侧 keepalive 超时断连)→重注册对账 handle_sync 仅按 container_id 匹配→pending 占位行判 destroyed、真容器 cf6b4df15119「未知忽略」成 docker 孤儿,任务 9001。修复=runner 上报补 task_id(qicheng.task_id label)+handle_sync 按 task 收养(真实 id 替换+UNIQUE 后缀+计数并入;双失配才判毁;快照迭代修正) | pytest 4/4(收养/UNIQUE/真毁回归/旧协议兼容);真机收养 E2E:db=1 reported=1,DB 行=cf6b4df15119/running,任务复活;对话/终端 9001 消除;用户复验通过 |
| BUG-056 | verified | R32.F5(R32.F3 流式特性延续;runner container_manager) | 两段:① R8.F5 热更不完整只拷 main.py,容器内 container_manager.py 旧镜像版缺 claude_prompt_stream(envelope 原文 no attribute)→全量四文件热更;② demux=False 裸读不剥 docker exec 非 tty 8 字节帧头(内容前缀 ..   污染)+ len(buf)<8 把 EOF 残 chunk(4 字节含 result 行尾 
)永久扣留丢末行。修复=双缓冲剥帧(stream∈{0,1,2}+填充校验只取 stdout)+EOF 冲刷+_drain_line_buf 闭包 | runner 全量 43/43(2 新用例:7 字节切块跨帧分片/stderr 帧隔离);真机 3.2s 返 pong 干净落库(tokens_out=14);用户复验通过 |

**遗留登记**:① runner 镜像重建被 Docker Hub 不可达阻塞(R31.F3 同款),本机容器经 docker cp 四文件热更,旧镜像重建容器会回退(R8.F5/R32.F5 两处修复失效但无新破坏),镜像重建后自愈——DEPLOY.md 发布动作;② 平台事件循环停滞窗口根因未定(疑与定时巡检重叠),登记观察;③ 全量 pytest 回归受共享测试库外部 contention 阻塞(1213 死锁 35 次/13min),隔离窗口单文件全绿,全量归 rd-check。

## rd-fix 第 30 轮迁移(2026-09-27,BUG-057/058;用户复验通过)

| BUG | 状态 | 关联 | 根因与处置 | 验证 |
|---|---|---|---|---|
| BUG-057 | verified | R32.F6(R32.F3 流式特性延续;后端 task_service) | TaskEventRegistry.connect 把 conn(dict)塞进 set → `TypeError: unhashable type: 'dict'` → /ws/tasks/{id}/events 端点 accept 后崩断(无关闭帧,ASGI 栈定罪)→ 注册表永远空 → broadcast 恒 conns=0(TEMP-PROBE 日志实证)——chat_delta/chat_done/tool_call/file_changed 全部任务事件推送自上线起对前端不可达。修复=registry 存 websocket 本体(dict[str,list]),connect/disconnect/broadcast 改造,对外契约不变 | pytest 5/5(收发/坏连接摘除/映射/回归);真机探针:对话期间事件 WS 收 14 帧(11 chat_delta + chat_done + 30s 心跳 ping),双向连通实证;用户复验通过 |
| BUG-058 | verified | R32.F6( runner container_manager + 平台映射) | runner claude_prompt_stream cmd 未加 --include-partial-messages(CLI 默认按 turn 整块);平台 _stream_event_to_chat 无 stream_event 映射。修复=cmd 加 flag(容器内 CLI 实证支持)+ 映射 stream_event/content_block_delta/text_delta → chat_delta(assistant 整块回退保留)。**整段呈现的终极根因为环境限制(另案)**:容器内直连上游网关 SSE 实测 2928 行 span=0.00s(800 词 59.10s 攒齐一次吐)——网关不支持流式;平台全链已就绪,网关开启流式或换流式网关即零改动变逐字输出 | runner 43/43(cmd 断言);真机探针 126 delta 可达;用户复验通过(活动流实时;整段/逐字随网关能力) |

**遗留登记(非平台代码 bug)**:上游 LLM 网关(token-console qwen)SSE 非流式——服务端攒齐完整响应一次性返回(实测 span=0.00s)。归用户网关侧处置(开启流式透传或更换网关);平台侧零改动自适应。

## rd-fix 第 31 轮迁移(2026-09-28,BUG-061 环境缺陷修复 + BUG-052 接线实证解决)

| BUG | 状态 | 关联 | 根因与处置 | 验证 |
|---|---|---|---|---|
| BUG-061 | verified | R34.F1(需求分支默认策略,commit 93242f9)依赖环境;修复分片 R34.F2 | 用户实测报障:需求创建 POST /api/projects/{pid}/requirements 500「服务器内部错误」。traceback 实锤=requirement_service.py L194 create_requirement→L173 default_req_branch→L146 gen_req_branch_slug 函数内 `from pypinyin import ...` 抛 ModuleNotFoundError。pyproject L21 已声明 pypinyin>=0.50,<1.0(uv.lock 锁 0.55.0),但本机运行时(E:\services\python310 system env)自 93242f9 后从未执行依赖安装;backend/venv 为空壳(空 site-packages 无解释器)加剧混淆;函数内延迟 import 使启动期不报错,首个创建请求才炸。**零代码修复**=定向补装 `pip install "pypinyin>=0.50,<1.0"`→0.55.0(与锁一致);`pip install -e .` 因 setuptools 包发现配置问题在 editable 构建阶段失败(独立打包问题未修,本机历来散装依赖);防御性建议(gen_req_branch_slug 加 ImportError 回退)留用户决策未实施 | pytest tests/test_r34_req_branch.py 16/16;真机重放(超管 JWT 铸造)POST 创建中文标题需求 → code=0,req_branch=feat/hgcsrzwbty20260928(拼音首拼 slug 10 字截断+8 位日期,正则 ^feat/[a-z]{1,10}\d{8}$;R34.F2 分片初稿正则 \d{4} 系笔误已勘正);测试行经 DELETE /api/requirements/{id} 删除(code=0);后端 uvicorn --reload 无需重启(延迟 import 调用时解析);证据 .scratch/R34.F2/verify.md |
| BUG-052 | verified(解决) | R34.F1(需求分支默认策略) | 登记时(2026-09-26)create_requirement L190 仍为 `req-{id8}` 回退,gen_req_branch_slug/default_req_branch 死代码;R34.F1 会话 commit 93242f9「需求分支默认策略 feat/{需求名首拼≤10}{日期}+接线」已完成接线(L194 现调 default_req_branch(title));本轮 BUG-061 回归真机实证拼音策略真实产出(feat/hgcsrzwbty20260928),原「未接线」缺口闭环。连带勘误:BUGS.md 原「ISSUES.md R34.F1 行表述与工作区代码不符」随接线完成自然消解 | 同 BUG-061 回归(同一链路:接线→拼音 slug→落库) |

## rd-fix 第 32 轮迁移(2026-09-28,BUG-062 依赖安装链加固;用户指令)

| BUG | 状态 | 关联 | 处置 | 验证 |
|---|---|---|---|---|
| BUG-062 | verified | —(工程化;修复分片 R34.F3;BUG-061 根因链延伸) | 用户指令「生成 requirements.txt 默认启动,安装好对应的依赖 -r requirements.txt」。落地:① `backend/requirements.txt`(14 项运行时,与 pyproject [project].dependencies 同源同约束逐字对应,文件头注明同步纪律)+ `backend/requirements-dev.txt`(-r requirements.txt + pytest/pytest-asyncio/httpx/ruff,对应 dev extras);② README 快速开始默认安装改 `pip install -r requirements-dev.txt`(仅运行时可只装 requirements.txt),留痕 `pip install -e .` 因 setuptools 包发现配置不可用;③ 执行安装(本机 E:\services\python310):安装前快照实证漂移——fastapi 0.104.0 低于声明 >=0.110、ruff 缺失、其余 13 项满足;安装后 fastapi→0.141.1、pydantic 2.5.3→2.13.5(+pydantic-core 2.46.5)、starlette→1.7.0、anyio→4.15.1、watchfiles/httptools 新装、ruff 0.16.9 补齐;④ 后端重启加载新栈 | ① 清单一致性:两文件与 pyproject 约束逐一比对一致;② pip install -r 两文件全绿;③ 新栈 /health ok、启动日志零异常;④ 真机重放(超管 JWT)需求创建 code=0、req_branch=feat/hgcsrylsjh20260928、测试行已删(证据 .scratch/R34.F2/verify.md § R34.F3);⑤ 全量 pytest 22 failed/838 passed 逐例隔离分类(报告 .scratch/R34.F3/pytest-analysis.md):**A 升级回归=0**——20 个=R32 Runner 标签流测试先行(create_runner(tags=)/validate_tags/update_runner 未实现,任何依赖状态都红,归属该流非本修)、2 个=环境噪音(测试环境 LLM 配置缺失 + bcrypt `__about__` setup error);判定 PASS → verified |

## rd-fix 第 35 轮迁移(2026-09-28,BUG-065 runner 容器旧镜像回退;两会话协同收口)

| BUG | 状态 | 关联 | 根因与处置 | 验证 |
|---|---|---|---|---|
| BUG-065 | verified | R8.F6(runner 运行时;承接第 29 轮「runner 镜像重建」遗留);登记会话报症状①(对话 9001),协同会话补症状②(打磨容器未启动)并完成根因定位+修复执行 | 根因两层:① 17:04 runner 容器从旧 platform/runner:v1 重建,第 29 轮 docker cp 热补(R8.F5 上报/R32.F5 流式)全部回退(容器代码与仓库 md5 不一致,留痕预言应验);② 16:58 打磨 start 指令发进濒死连接丢失,占位行挂 creating 无兜底。修复=BASE_IMAGE=python:3.10 回退重建 runner:v1(R31.F3 文档化路径)+原参数重建容器(md5 与仓库逐字节一致);后继深挖:对话空回复=「R34.F3 权限桥接 --permission-prompt-tool + 任务会话被容器内交互 claude 占用」→ bridge.py 阻塞 stdin、runner recv 无限挂——加 120s 超时守卫(runner/main.py,超时 cancel_claude+回报 stream_timeout)+清空 977/978 残留 claude_session_id;占位行经 handle_sync 判 destroyed 自愈。证据链:DEVPLAN/R8.F6.md、.scratch/R8.F6/{hang-analysis,hang-fix}.md、.scratch/R34.F2/verify.md § BUG-065 | ① 容器代码与仓库 md5 一致;② 真机消息 POST code=0、assistant="pong" 真实落库(tokens_in=49398/out=18);③ 977 打磨容器 running+新会话首聊成功;④ 遗留占位行判毁;⑤ 两会话各自独立复验通过。附带留痕:claude CLI 2.1.280 对 qwen3.7-plus 报 unrecognized_model 警告(仅 stderr 不拦截,可 CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1 消音);建议 runner 镜像重建进 DEPLOY.md 检查单(热更不持久第二次踩坑) |

## rd-fix 第 41 轮迁移(2026-09-29,BUG-073 容器泄漏 4 路径收口 R3.F3;用户报障)

| BUG | 状态 | 关联 | 根因与处置 | 验证 |
|---|---|---|---|---|
| BUG-073 | verified | R3.F3(新建修复分片;诊断底稿 .scratch/fix-analysis.md § BUG-073) | 用户报障「窗口管理泄漏:任务跑一段时间容器会比任务多」。诊断实证 4/4 运行容器全孤儿(running 任务 0),4 条泄漏路径:①retry_task 不清旧容器叠新;②request_stop 下发即返回无超时兜底(DB+docker 双驻留);③Runner 离线分支只标 stopped 不销毁(「待 R16 对账」未实现);④lifespan 启动无孤儿对账;助收漏点=finish_task/sweep_timeouts 收容器 limit(1) 漏历史行。修复五子项:F2.a request_stop 等回报+60s 超时置 destroyed / F2.b Runner 重连补发 stop(接入 runner_ws register) / F2.c retry 前清旧 running/creating 行 / F2.d 启动对账(fail-safe:inspect 无结论仅抑制直接销毁,task 终态→create_task 后台并发补发 stop 不阻塞 lifespan) / F2.e finish/sweep 收所有 running 非 limit(1)。执行中打回两轮:①inspect 占位返回 None 会把活容器全误标 destroyed→fail-safe 化;②「无结论」跳过了补发 stop 分支→逻辑重排 | ①单测 test_bug073_container_leak.py 14/14(两轮打回各补用例)+触碰面 test_container_platform 25/25 串行;②真机对账:4 孤儿容器经用户批准 docker stop+rm→修正版重启→0a2bf2449cb2/5cf413bb2dda/9b13fe6af4a9 destroyed_at=13:48:50(=启动对账 13:47:50 派发+60s 兜底,F2.d+F2.a 活体实证)、2173ba6b17e7 destroyed_at 与用户 13:52 retry started_at 同刻(F2.c 活体实证);③docker 侧仅剩合法容器(wonderful_austin=用户活跃重试任务、qicheng-runner),Runner 看门狗复活现象(13:34 曾按 DB running 复活 2 容器)随 DB 行收敛未再现;④冒烟 /docs 200、无 5xx。附带留痕:main.py lifespan 缺 async_session_factory import(单测 mock 掩盖,真机启动 NameError,主会话直修一行);830af6e6 用户 13:25 修复前重试致「running 任务无容器」(归用户页面停止或重试);retry 不清 finished_at(观察项);Runner 看门狗按 DB 状态复活容器的机制未读码定位(观察项) |

## BUG-072 | 任务 AI 对话 MCP 工具调用无响应 | ✅ verified(2026-09-29 第 41 轮,rd-fix 第 40/41 轮)

- **关联**:R5.F3(对话链路权限;波及 R34.F3 权限桥接 4dc7d45 / R17 MCP 配置)
- **症状**:任务 AI 对话让 AI 使用 mysql_dev(MySQL MCP)无响应(空结算占位)
- **排除**:mysql_dev 本身健康——配置 `${ENV_MCP_MYSQL_*}` 键一致、`claude mcp list` Connected、3306 TCP 通、凭据用户 10:51 自配
- **根因(权限层,最终三层)**:
  1. 无桥接降级路径:headless 默认 permissionMode,MCP 工具触发 permission_denied 无人应答静默拒绝
  2. 桥接路径:R34.F3 用 `--mcp-config /tmp/permgate/mcp.json --permission-prompt-tool mcp__permgate__approval`——CLI 2.1.280 下 permgate server connected 但 approval 工具不进可用列表(实测 43 项),每个 MCP 调用 `tool_use_error: MCP tool mcp__permgate__approval not found`
  3. 第 40 轮 F2 合并 ~/.claude.json 形态**同样失效**(容器内复刻复现)——该 CLI 版本下 --permission-prompt-tool 引用 MCP 工具的机制整体不可用;坏 flag 在位时即使用户会话正常也 7s 空结算(用户 14:44 复现)
  4. 叠加自愈缺口:--resume 不存在的会话时 CLI 输出**单行 error-result**(is_error=true,非零行),R32.F8「零行降级」判定漏掉该形态(BUG-067②)→ 毒化会话每条消息秒败
- **修复(R5.F3 终态)**:
  - F1 cmd 追加 `--allowedTools` 放行 MCP 工具面(mysql_dev/beta/filesystem/brave-search/figma/github + 3 资源工具;任务对话=授权环境;mysql_query 具写库能力留痕接受)
  - 二修:stream 链路**彻底摘除 --permission-prompt-tool**(container_manager.py perm_flag 恒空),main.py 不再注入桥/起轮询(perm_ok=False);需审批工具(Bash/Edit/Write)维持静默拒绝;桥恢复归 CLI 升级/换实现
  - 三修(自愈):解析器识别 error-result → resume_error=True(errors 折入 stderr_tail);降级条件扩为 `(lines==0 or resume_error)`;后端结算时 resume_error → 置空 tasks.claude_session_id(免毒化会话每条双跑)
- **验证**:runner pytest 95/95(新增 test_bug072_resume_error 2 例 + r32 断言补键);容器内直调 SELECT 1→[{"test_col":1}] ×2;**端到端:平台 API 发「用 mysql_dev 查 SELECT 1」→ assistant 5s 落库「查询结果是 **1**。」**(runner 日志无降级线,resume 直接成功);镜像重建+容器重建 ×2;后端单进程重启
- **留痕**:① devbox:v2 镜像的 R9.F3 hasCompletedOnboarding 修复仍待 devbox 镜像重建(发布动作);② MCP server 启动有短暂 pending 窗口(模型过早调用看不到工具,提示等待即可);③ 运行环境 B.1 桥接注入实验遗留 permgate 键于部分容器 .claude.json(惰性无害,新容器不再注入);④ 修复涉及 backend task_service.py(会话自清)为第 41 轮新增,后端已重启加载
- **报告**:docs/20260920_ai_web开发平台/.scratch/R5.F3/fix_report.md(含主会话补充验证)

## BUG-075 迁移(2026-09-29,rd-ui 容器门卫核对轮附带发现;环境缺陷即时修复)

| BUG | 状态 | 关联 | 根因与处置 | 验证 |
|---|---|---|---|---|
| BUG-075 | verified | —(环境缺陷;零代码修复,BUG-061 pypinyin 同类) | 创建需求接口 500:代码用 `ZoneInfo("Asia/Shanghai")`,Windows 运行时缺 `tzdata` 包 → `ZoneInfoNotFoundError`。核对 agent 超管复现实证后处置:`uv pip install tzdata` 装入 backend/.venv(2026.4)+ 后端重启加载 | ① `ZoneInfo('Asia/Shanghai')` 本机验证 OK;② 重启后超管真机创建需求 200 成功(原 500);③ 留痕:tzdata **未声明**在 pyproject/requirements(BUG-061 requirements 同步纪律的漏网项)——建议 rd-dev 把 tzdata 补进依赖清单,否则换机/重建 venv 必复发;④ 复测用需求「BUG-075复测-可删」(07d2a0b1)已取消,平台无硬删,留系统(标题自带可删标识) |

## rd-fix 第 44 轮迁移(2026-09-30,BUG-077 需求详情关联任务创建时间空显;4 环断链修复)

| BUG | 状态 | 关联 | 根因与处置 | 验证 |
|---|---|---|---|---|
| BUG-077 | verified | R22.F3 波及(混合类型任务列表);复现 /requirements/0d227c83 | 四环断链:①requirement_service.py:224-232 tasks 子列表未返 created_at/display_status ②RequirementTaskBrief schema 缺字段 ③前端 RequirementTask 接口缺 created_at ④RequirementDetail.tsx:482 渲染处硬编码「—」(从未接线)。数据层本就有值(DB 实证),纯链路丢字段。修复=四环补齐+test_bug077_requirement_task_created_at.py 3 用例 | ①pytest 3/3+触碰面 16 passed 串行;②一轮假波折留痕:首验活体仍空显,仲裁发现 **8000 端口 0.0.0.0+127.0.0.1 双绑定**——localhost 永远命中 loopback 老进程(修复被误判无效),清杀后唯一监听=新代码;③终验:活体 API tasks[0].created_at 非空+display_status 非空,页面创建时间显示 2026/9/29,截图 report/rd-fix-r44/01-created-time.png。附带:ProjectTaskList.tsx:135 `data possibly undefined` 预存 tsc 错(R3.F1 期遗留,非本轮夹带),登记待修 |
