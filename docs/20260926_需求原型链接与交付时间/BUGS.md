# BUGS.md — 活跃问题清单

> 项目:需求原型链接与交付时间 | 更新:2026-09-27(BUG-013 verified 已迁移)(BUG-011 verified 已迁移)
> 状态流转:open → fixed → verified(verified 后迁移至 ISSUES.md)

| BUG | 状态 | 关联需求点 | 类型 | 来源 | 摘要 |
|---|---|---|---|---|---|
| BUG-010 | open | 待定(测试基建) | 低危(测试告警) | rd-fix BUG-009 修复顺带发现 2026-09-27 | backend/tests/conftest.py:153 附近 alembic 迁移回退路径存在未 await 协程(run_async_migrations),与产品代码无关,仅影响测试运行告警;低危待排期 |

## BUG-010

- **状态**:open
- **关联需求点**:待定(测试基建,非产品缺陷)
- **严重程度**:低(不影响产品行为,仅测试进程告警;测试套件当前全绿)
- **复现步骤**:跑 backend 测试套件,观察 conftest.py:153 附近的 RuntimeWarning
- **根因**:alembic 迁移回退路径中 `run_async_migrations` 协程未被 await
- **修复方案**:补 await 或按 conftest 异步惯例包装;1-2 行级修复
- **涉及文件**:backend/tests/conftest.py(:153 附近)

## BUG-012

- **状态**:open
- **关联需求点**:待定(存量缺陷,删除分析顺带发现)
- **严重程度**:一般(发布页「已部署」筛选功能失效)
- **复现步骤**:/manage/releases 状态筛选选「已部署」→ 列表空(即使存在已部署成功的发布任务)
- **期望 vs 实际**:期望筛出已部署发布任务;实际永远空集
- **根因**:筛选项值 `deployed` 不在 Task.status 枚举;实际落库为 status='done' + extended_attributes.deploy_phase='deployed';dashboard_views.py:146 是裸 `Task.status == status` 等值过滤
- **修复方案**:候补——①筛选项改值/映射为 done+deploy_phase 复合条件;或 ②移除该筛选项。需用户定夺口径
- **涉及文件**:frontend/src/pages/manage/ManagePages.tsx(:38-41)、backend/app/services/dashboard_views.py(:146)

