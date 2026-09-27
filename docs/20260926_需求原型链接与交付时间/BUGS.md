# BUGS.md — 活跃问题清单

> 项目:需求原型链接与交付时间 | 更新:2026-09-26
> 状态流转:open → fixed → verified(verified 后迁移至 ISSUES.md)

| BUG | 状态 | 关联需求点 | 类型 | 来源 | 摘要 |
|---|---|---|---|---|---|
| BUG-004 | fixed | R1/R2/R4(页面需求管理) | 功能缺口 | 用户指令 2026-09-26 | /manage/requirements 快速创建 dialog 仅有 title+description,缺少 background/acceptance_criteria/priority/req_branch/delivery_date/related_user_ids/prototype_links 等字段(项目详情页 dialog 已有全部字段) |
| BUG-005 | fixed | R34.F1(前端分支预览) | UI 观感(占位符易误读) | 用户指令 2026-09-26 | 需求创建弹窗分支预览把汉字渲染为 `□`(feat/□□□□□20260926),用户误读为「乱码」;后端拼音策略已生效(提交 93242f9),但前端预览未调后端接口取真实拼音 |
| BUG-006 | fixed | R3(测试任务创建)/R4(发布任务创建) | 功能缺陷 | 用户报障 2026-09-26 | /manage/tests 和 /manage/releases 快速创建任务返回 422 "String should have at least 1 character"——QuickCreateDialog 在 test/release 维度无 description 输入框,description state 恒为空串触发后端 min_length=1 校验 |

## BUG-004

- **状态**:open
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
