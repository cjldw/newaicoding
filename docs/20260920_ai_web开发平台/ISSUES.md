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

## 登记遗留(2026-09-24,rd-fix 第 20 轮)

| 项 | 描述 | 建议归属 |
|---|---|---|
| BUG-044(R31 并行会话工作区,未代修) | test_r31_local_runner 10 failed/2 errors:① delete local 链路把 AsyncMock/未序列化对象写入 audit_log.detail(JSON 序列化炸,PendingRollbackError 实证);② conftest 的 alembic upgrade 失败(fallback create_all,疑 R31 迁移记账漂移);③ runners.py 曾出现装饰器与注释粘行致 reset-token 404(本轮已修,疑两会话编辑碰撞) | R31 并行会话收口时处理 |

## rd-fix 第 20 轮迁移(2026-09-24)

| BUG | 状态 | 关联 | 根因与修复 | 验证 |
|---|---|---|---|---|
| BUG-043 | verified | R31.F1 | 非容器 runner 无终端通道(R26 终端=exec 进自身容器;R31 本机裸跑 runner 成一级能力后缺口凸显)。宿主 shell 降级通道:terminal_manager.py HostSession(subprocess,Windows=cmd.exe/Linux=bash,read1 防凑满阻塞)+ main.py exec "__host__" 哨兵分流 + runners.py 空串分支建 host 会话(键缺失仍 6003);审计 session_kind=runner_host;前端零改动 | runner 单测 6/6(真进程 echo/stdin/kill);后端 r26 11/11 + 触碰面 47 绿;真机:reset-token→新 token 重拉 runner-local→shell-sessions code=0(会话已关)。Windows 管道模式无 pty(resize/真 TTY 降级)接受 |
