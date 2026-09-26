# BUGS:需求关联用户/评审通知 + 原型链接/交付时间(rd-check 首轮)

> 创建日期:2026-09-26 | 来源:rd-check 首轮 | 接口级 bug:0 | 规格缺口:2 | 环境阻塞:3(不写 BUG,见 CHECKREPORT)

## BUG-001
- **状态**:open(规格缺口,流向 rd-plan 契约收口)
- **关联需求点**:R4
- **严重程度**:轻微
- **复现步骤**:POST /api/projects/{pid}/requirements,body 含 prototype_links=[{label,url},…](合法值);响应 data 仅 {req_id, req_branch}
- **期望 vs 实际**:期望(执行脚本按「创建回显」理解)创建响应含 prototype_links 回显;实际仅创建最小契约。分片 R4.md 书面回显契约在**详情**响应(GET /requirements/{id},已通过);落库正确。判定:分片未规格化创建响应回显 → 契约补齐问题,非实现缺陷
- **错误信息**:无(结构缺失,4 轮稳定复现)
- **来源**:rd-check 接口断言(.scratch/check/R4/result.md)

## BUG-003
- **状态**:open
- **关联需求点**:R1(计划外发现)
- **严重程度**:轻微
- **复现步骤**:读 backend/app/api/requirements.py:236——`require_project_role(...)` 调用缺 `await`,协程未被消费
- **期望 vs 实际**:期望 await 生效的角色校验;实际为死调用。现状无越权洞(外层 owner 校验兜底),属潜伏缺陷
- **错误信息**:无(静态发现,判据抽查独立复核时定位)
- **来源**:rd-check 判据抽查(.scratch/check/R1/criteria.md)

## BUG-002
- **状态**:open(规格缺口,流向 rd-plan 契约收口)
- **关联需求点**:R7
- **严重程度**:轻微
- **复现步骤**:GET /api/dashboard/summary(第二角色身份,其关联需求出现在 recent 列表)
- **期望 vs 实际**:期望(R7.md 接口契约)recent 行透传 `delivery_date/related` 两个字段;实际仅透传 `delivery_date`,`related` 不存在;frontend/src/api/dashboard.ts 的 RecentRequirement 与 Dashboard.tsx 均未引用 `related` → 零功能影响
- **错误信息**:无(字段缺失,真实环境复现)
- **来源**:rd-check 接口断言(.scratch/check/R7/result.md #21)
