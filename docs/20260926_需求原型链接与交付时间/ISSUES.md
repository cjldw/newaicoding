# ISSUES.md — 已解决问题归档

> 项目:需求原型链接与交付时间 | 创建:2026-09-27(由 BUGS.md verified 条目迁移)

> 来源:rd-fix 修复循环;回归判据见 .scratch/regression-R2.md

| BUG | 状态 | 关联需求点 | 类型 | 来源 | 摘要 |
|---|---|---|---|---|---|
| BUG-004 | verified | R1/R2/R4(页面需求管理) | 功能缺口 | 用户指令 2026-09-26 | /manage/requirements 快速创建 dialog 补齐完整字段(2026-09-27 回归 verified) |
| BUG-005 | verified | R34.F1(前端分支预览) | UI 观感 | 用户指令 2026-09-26 | 分支预览改调后端拼音接口,消除 □ 误读(2026-09-27 回归 verified,实测 feat/yhdl20260927) |
| BUG-006 | verified | R3/R4(测试/发布任务创建) | 功能缺陷 | 用户报障 2026-09-26 | test/release 快速创建 422:description 兜底+校验放宽(2026-09-27 回归 verified) |
| BUG-007 | verified | R2.F1(需求列表编辑入口) | 功能缺口 | 用户报障 2026-09-27 | /manage/requirements 操作列新增「编辑」+ RequirementEditDialog,分支名/PRD 路径不可改(2026-09-27 回归 verified) |
| BUG-008 | verified | R2.F2(任务三维编辑) | 功能缺口 | 用户报障排查确认 2026-09-27 | 三维操作列「编辑」+ 后端 PATCH /api/tasks/{task_id}(pending 守卫/端口唯一/字段面受控)(2026-09-27 回归 verified) |

## BUG-004

- **状态**:fixed(2026-09-27 代码级核实已落地,详见 .scratch/fix-analysis.md;待回归)
- **关联需求点**:R1(关联用户)/R2(交付时间)/R4(原型链接) — 页面需求管理入口
- **严重程度**:一般(功能缺口,/manage/requirements 创建需求时无法填写交付时间、原型链接等字段)
- **复现步骤**:
  1. 访问 /manage/requirements
  2. 点击「新建需求」按钮
  3. 观察弹窗字段
- **期望 vs 实际**:
  - 期望:弹窗包含与项目详情页需求创建 dialog 一致的完整字段(title/background/description/acceptance_criteria/priority/req_branch/delivery_date/related_user_ids/prototype_links)
  - 实际:弹窗仅有 title + description 两个字段(QuickCreateDialog 快速创建模式)
- **根因**:`DimensionPage.tsx` 的 `QuickCreateDialog` 为四维通用快速创建,requirements 维度仅提交 title+description;项目详情页 `RequirementList.tsx` 的创建 dialog 已实现全部字段
- **修复方案**:将 `/manage/requirements` 的创建 dialog 替换为与 `RequirementList.tsx` 同构的完整表单(保留项目选择器,因为 manage 页面跨项目);复用 `RelatedUserSelect` 组件;prototype_links 行组逻辑照搬
- **涉及文件**:
  - `frontend/src/pages/manage/DimensionPage.tsx`(QuickCreateDialog 改造或替换)
  - 可能需要抽取 RequirementList.tsx 的表单为公共组件复用
## BUG-005

- **状态**:fixed
- **关联需求点**:R34.F1(前端分支预览)
- **严重程度**:一般(UI 观感问题)
- **复现步骤**:
  1. 访问 `/projects/{pid}/requirements` 或 `/manage/requirements`
  2. 点击「新建需求」按钮
  3. 在标题输入框输入中文标题(如「用户登录功能优化」)
  4. 观察分支预览显示
- **期望 vs 实际**:
  - 期望:分支预览显示真实拼音(如 `feat/yhdl20260926`)
  - 实际:分支预览显示 `□` 占位符(如 `feat/□□□□□20260926`),用户误读为「乱码」
- **根因**:`RequirementList.tsx` L109-120 的 `branchPreview` 本地计算逻辑,汉字 map 成 `'□'`(注释注明「汉字以□占位提示,后端权威」)。后端拼音策略已生效(提交 93242f9,`default_req_branch(title)` 返回 `feat/yhdlgnyh20260926`),但前端预览未调后端接口取真实拼音。
- **修复方案**:
  - 后端新增 `GET /api/requirements/branch-preview?title=...` 接口,返回真实拼音分支
  - 前端 `RequirementList.tsx` 和 `DimensionPage.tsx` 的分支预览改为调用后端接口(debounce 300ms)
  - 删除 `□` 占位符和误导文案,显示真实拼音如 `feat/yhdl20260926`
- **涉及文件**:
  - `backend/app/api/requirements.py`(新增 branch-preview 接口)
  - `frontend/src/api/requirements.ts`(新增 branchPreview 方法)
  - `frontend/src/hooks/useDebounce.ts`(新建共享防抖 hook)
  - `frontend/src/pages/requirements/RequirementList.tsx`(预览改为调接口)
  - `frontend/src/pages/manage/DimensionPage.tsx`(RequirementCreateDialog 预览改为调接口)
- **验证结果**:
  - TypeScript 编译零错误
  - TestClient 端到端实测:`title=用户登录` → 200 `{"branch": "feat/yhdl20260926"}`
  - 待浏览器实测:输入中文标题,验证预览显示真实拼音
## BUG-006

- **状态**:fixed
- **关联需求点**:R3(测试任务创建)/R4(发布任务创建)
- **严重程度**:严重(功能缺陷,阻塞任务创建)
- **复现步骤**:
  1. 访问 `/manage/tests` 或 `/manage/releases`
  2. 点击「新建测试任务」或「新建发布任务」按钮
  3. 选择需求后直接点击「创建」
  4. 观察报错
- **期望 vs 实际**:
  - 期望:创建成功,返回 200 + task_id
  - 实际:返回 422 `{"code": 422, "data": null, "message": "String should have at least 1 character"}`
- **根因**:`DimensionPage.tsx` 的 `QuickCreateDialog` 在 test/release 维度:
  1. **没有 description 输入框**(test 维度 L529-534 只渲染需求下拉 + hint;release 维度类似)
  2. `description` state 恒为 `''`
  3. 提交 payload 无差别组装 `description: description.trim()`(L432-436)→ 恒发空串
  4. 后端 `CreateTaskRequest`(`tasks.py:89-92`)的 `description: str = Field(min_length=1)` 必填
  5. `canSubmit`(L458-463)对 test/dev/release 维度只校验 `!!reqId`,不拦空描述
  - title 有 `|| req.title` 兜底所以没事,description 没有兜底
  - 另外 title `.slice(0, 200)` 与后端 `max_length=128` 不一致,需求标题超 128 字会报第二个 422
- **修复方案**:
  - 前端:QuickCreateDialog test/release 分支 description 兜底(`description.trim() || req?.title || '任务描述'`) + title slice 对齐 128
  - 后端:`CreateTaskRequest.description` 放宽为可选 + API 层按类型落默认文案(`f"{type_label}需求:{req.title}"`)
  - 后端:422 处理器带字段名(message 前缀 + `data.field`)
  - 计划外修复:`runner_service.py` 补 R32 半成品接线(`ALLOWED_TASK_TAGS` 常量 + `pick_runner_db` 参数)
- **涉及文件**:
  - `frontend/src/pages/manage/DimensionPage.tsx`(QuickCreateDialog description 兜底 + title slice 对齐)
  - `backend/app/api/tasks.py`(CreateTaskRequest description 放宽校验)
  - `backend/app/core/response.py`(422 处理器带字段名)
  - `backend/app/services/runner_service.py`(补 R32 半成品接线)
- **验证结果**:
  - TypeScript 编译零错误
  - pydantic 边界矩阵直验:不传 description→None、空串→''(均走兜底文案)、2000 字通过、2001/标题 129→422,全部符合预期
  - pytest:`test_test_tasks` 修复前 3 failed → 修复后 2 个通过、剩余 2 个失败为 MySQL 1213 死锁(与并行会话争用共享测试库有关)
  - 待浏览器实测:`/manage/tests`、`/manage/releases` 快速创建(超 128 字标题需求 + 不填描述),验证 200 + 跳转 `/tasks/{id}` + 描述为需求标题
  - `runner_service.py` 的 16 行改动未提交,建议单独入库
## BUG-007

- **状态**:fixed(2026-09-27 修复完成,串行 pytest 56 passed + tsc 零错误;待回归)
- **关联需求点**:R2.F1(/manage/requirements 列表编辑入口)
- **严重程度**:一般(功能缺口,创建后无任何修改通道)
- **复现步骤**:
  1. 访问 /manage/requirements
  2. 观察任意需求行的操作列
- **期望 vs 实际**:
  - 期望:操作列有「编辑」按钮;可修改标题/背景/描述/验收标准/优先级/交付时间/关联用户/原型链接;分支名(req_branch)与 PRD 路径不可修改(关联 GitLab 分支)
  - 实际:操作列只有跳转箭头(DimensionPage.tsx L202/L211-214,整行点击跳详情);需求详情页也仅能改关联用户+交付时间,其余字段无处可改
- **根因**:四维共用 DimensionPage.tsx 操作列无按钮,编辑 dialog 从未实现;项目详情页 RequirementList.tsx 同样只有创建 dialog;后端 PATCH /api/requirements/{req_id}(requirements.py:123-161)已具备全部可改字段且 req_branch/prd_file_path 不在 UpdateRequirementRequest schema 中(天然不可改),前端 requirementsApi.update 契约齐全但无消费入口
- **修复方案**:见 DEVPLAN/R2.F1.md(操作列「编辑」+ RequirementEditDialog,恒传 delivery_date 防缺省置 NULL;后端零改动)
- **涉及文件**:frontend/src/pages/manage/DimensionPage.tsx(操作列+编辑弹窗);后端无改动
## BUG-008

- **状态**:fixed(2026-09-27 修复完成,新增 test_tasks_update.py 8 用例 Red→Green;待回归)
- **关联需求点**:R2.F2(任务三维编辑)
- **严重程度**:一般(功能缺口;任务字段创建后无任何修改通道)
- **复现步骤**:
  1. 访问 /manage/tasks、/manage/tests、/manage/releases
  2. 观察任意任务行的操作列(现状:均无操作按钮)
  3. curl -X PATCH /api/tasks/{id}(现状:404/405,接口不存在)
- **期望 vs 实际**:
  - 期望:三维列表操作列有「编辑」;pending 任务可改字段(通用 title/description + dev 分支/release 部署字段);type/req_id/status 不可改
  - 实际:前端操作列无按钮(DimensionPage.tsx L202/L211-214);后端 tasks.py 全部端点无 PATCH/PUT(L35-547);前端 api/tasks.ts 无 updateTask——两层都不存在
- **根因**:与 BUG-007 同根因(共用操作列无按钮);任务维后端从未实现 update 接口,非"漏接"
- **修复方案**:见 DEVPLAN/R2.F2.md(后端新增 PATCH /api/tasks/{task_id} + UpdateTaskRequest,pending 守卫、release 端口唯一校验;前端 updateTask + TaskEditDialog 按 type 出字段)
- **涉及文件**:backend/app/api/tasks.py、frontend/src/api/tasks.ts、frontend/src/pages/manage/DimensionPage.tsx

| BUG-009 | open | 待定(R9?) | 安全隐患(既有) | rd-fix 回归轮独立抽查 2026-09-27 | backend/app/api/requirements.py:254 cancel 端点存在 `require_project_role` 协程未 await 的 RuntimeWarning——权限校验可能未实际执行(viewer 或可取消需求),需代码核实并修复 |

| BUG-009 | verified | R2.F3(requirements cancel 权限) | 安全隐患(既有) | rd-fix 回归轮独立抽查 2026-09-27 | cancel 端点裸调 async require_project_role 未 await,viewer guard 死代码;补 await 1 行修复,owner-only 规则保持(2026-09-27 verified,Red→Green+31 passed) |

## BUG-009

- **状态**:open
- **关联需求点**:待定(既有代码隐患,非本轮分片引入)
- **严重程度**:较高(若属实为权限绕过:无 editor 角色也可能取消需求)
- **复现步骤**:
  1. 调用 POST /api/requirements/{req_id}/cancel(或对应取消端点,requirements.py:254 附近)
  2. 观察服务端日志 RuntimeWarning: coroutine 'require_project_role' was never awaited
- **期望 vs 实际**:
  - 期望:非 editor 角色调用被 403 拒绝,权限依赖正常生效
  - 实际:回归轮抽查发现该端点有未 await 协程的 RuntimeWarning,权限校验疑似未执行
- **根因**:待核实——可能为 `require_project_role(...)` 被当普通函数调用而未走 Depends/未 await
- **修复方案**:先代码核实(读 requirements.py cancel 端点与 require_project_role 定义);若属实:补 await 或改 Depends 用法,并补测试(viewer 取消 → 403,editor → 200);若为误报(如实际是 Depends 注解用法,警告来自别处):出具证据关闭本条
- **涉及文件**:backend/app/api/requirements.py(:254 附近)、backend/tests/(新增或就近补用例)

| BUG-011 | verified | R4.F1/R4.F2(四维删除操作) | 功能缺口 + 数据安全守卫 | 用户指令 2026-09-27 | 需求/任务/测试/发布列表「删除」+ 后端 DELETE 端点:需求 owner+approved 后禁删+关联任务禁删;任务严档仅 pending 无容器/消息可删,release 发布完成提示先下线;硬删+级联+审计(2026-09-27 回归 verified:80 passed、API 抽查 19/19) |

## BUG-011

- **状态**:fixed(2026-09-27 修复完成:两端点+16 用例 Red→Green,串行 pytest 74 passed、tsc 零错误;待回归)
- **关联需求点**:R4.F1(需求删除)/R4.F2(任务三维删除)(待建)
- **严重程度**:一般(功能缺口)+ 守卫设计需从严(删除为破坏性操作)
- **复现步骤**:
  1. 访问四维 manage 列表,观察操作列(现状:仅「编辑」+ chevron,无删除)
  2. curl -X DELETE /api/requirements/{id} 与 /api/tasks/{id}(现状:预计 404/405,待分析核实)
- **期望 vs 实际**:
  - 期望:操作列新增「删除」(确认弹窗);仅可删"无关联、未产生数据"的记录——需求:评审通过不可删(且有关联任务不可删);任务/测试:进行中不可删;发布:发布完成不可删;后端 DELETE 端点带同口径守卫,前端按钮态与后端一致
  - 实际:前端无删除入口;后端删除端点缺失(待分析核实)
- **根因**:与 BUG-007/008 同族——操作列与 CRUD 链路从未实现删除侧
- **修复方案**:见 DEVPLAN/R4.F1.md、R4.F2.md(建分片后回填);守卫从严默认:不可删状态集合与关联数据检查后端强制,前端仅做按钮态镜像
- **涉及文件**:backend/app/api/requirements.py、backend/app/api/tasks.py、frontend/src/pages/manage/DimensionPage.tsx、frontend/src/api/requirements.ts、frontend/src/api/tasks.ts(以分析为准)

| BUG-012 | open | 待定(R4.F3?) | UI 缺陷(存量) | rd-fix 删除分析顺带发现 2026-09-27 | 发布维状态筛选项「已部署」用了不存在的 `deployed` 状态值(ManagePages.tsx:38-41),而 Task.status 枚举无此值——部署成功实际写 done+deploy_phase=deployed(task_service.py:1075-1077),dashboard_views.py:146 裸等值过滤,选「已部署」永远查不到行 |

| BUG-013 | verified | R5.F1(项目详情页需求列表编辑/删除) | 功能缺口 | 用户指令 2026-09-27 | 项目详情页(/projects/{pid})需求行补「编辑」「删除」;抽取 RequirementEditDialog 共享组件,manage 四维与项目维两页物理共用同一弹窗(2026-09-27 verified:tsc 零错误、后端 14 passed、ui-check 含两页语义一致性) |

## BUG-013

- **状态**:open
- **关联需求点**:R5.F1(项目详情页需求列表编辑/删除)
- **严重程度**:一般(功能缺口;与 BUG-007/011 同族,manage 维已修,项目维未同步)
- **复现步骤**:访问 /projects/{pid} 需求列表 → 行内无编辑/删除操作
- **期望 vs 实际**:期望行内操作列有「编辑」「删除」,口径与 manage 四维一致;实际无任何操作入口
- **根因**:R2.F1/R4.F1 只改造了 DimensionPage(manage 四维),项目详情页 RequirementList.tsx 未同步
- **修复方案**:见 DEVPLAN/R5.F1.md;后端零改动
- **涉及文件**:frontend/src/pages/requirements/RequirementList.tsx(主)、DimensionPage.tsx(若抽共享组件)
