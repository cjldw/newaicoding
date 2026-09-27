# DEVPLAN:需求原型链接与交付时间

> 创建日期:2026-09-26
> 当前进度:R2/R4/R5 三轮全部闭环(BUG-007~011、013 verified 归档);BUGS.md 仅剩待定夺项:BUG-010(低危测试基建)、BUG-012(发布页「已部署」筛选失效)(2026-09-27)

## 需求点清单

| 编号 | 描述 | 关联 BUG | 状态 | 详情文件 |
|---|---|---|---|---|
| R1.F1 | /manage/requirements 新建需求 dialog 补齐完整字段(对齐项目详情页) | BUG-004 | ✅ | ./DEVPLAN/R1.F1.md |
| R1.F2 | 需求创建弹窗分支预览改为调后端接口取真实拼音(消除 □ 误读) | BUG-005 | ✅ | ./DEVPLAN/R1.F2.md |
| R1.F3 | /manage/tests 和 /manage/releases 快速创建任务 422 报错(description 空串触发 min_length=1) | BUG-006 | ✅ | ./DEVPLAN/R1.F3.md |
| R2.F1 | /manage/requirements 列表操作列新增「编辑」+ 需求编辑弹窗(分支名/PRD 路径不可改) | BUG-007 | ✅ | ./DEVPLAN/R2.F1.md |
| R2.F2 | 任务三维列表编辑 + 后端新增 PATCH /api/tasks/{task_id}(pending 守卫、release 端口校验) | BUG-008 | ✅ | ./DEVPLAN/R2.F2.md |
| R2.F3 | requirements cancel 端点权限协程未 await(回归轮新发现) | BUG-009 | ✅ | ./DEVPLAN/R2.F3.md |
| R4.F1 | 需求列表「删除」+ 后端 DELETE /api/requirements/{req_id}(owner/状态/关联三级守卫) | BUG-011 | ✅ | ./DEVPLAN/R4.F1.md |
| R4.F2 | 任务三维列表「删除」+ 后端 DELETE /api/tasks/{task_id}(pending 严档守卫) | BUG-011 | ✅ | ./DEVPLAN/R4.F2.md |
| R5.F1 | 项目详情页需求列表(/projects/{pid})编辑+删除(纯前端,复用 R2/R4 后端) | BUG-013 | ✅ | ./DEVPLAN/R5.F1.md |

## 实施记录

- 2026-09-26:R1.F1/R1.F2/R1.F3 实施完成(BUG-004/005/006 代码级核实已落地,见 .scratch/fix-analysis.md;进度表当时未同步,2026-09-27 补记),待回归
- 2026-09-27:R2.F1/R2.F2 实施完成(R2.F1 前端编辑弹窗+操作列;R2.F2 后端 PATCH /api/tasks/{task_id} +86 行、test_tasks_update.py 8 用例 Red→Green;串行 pytest 56 passed、tsc 零错误;ui-check 两份通过),待回归

## 变更记录

| 日期 | 变更内容 | 来源 |
|---|---|---|
| 2026-09-26 | 新增 R1.F1 修复 BUG-004 | 用户指令 |
| 2026-09-26 | 新增 R1.F2 修复 BUG-005 | 用户指令 |
| 2026-09-26 | 新增 R1.F3 修复 BUG-006 | 用户报障 |
| 2026-09-27 | 新增 R2.F1 修复 BUG-007(/manage/requirements 编辑入口) | 用户报障 |
| 2026-09-27 | 新增 R2.F2 修复 BUG-008(任务三维编辑 + 后端 update 接口) | 用户报障排查确认 |
| 2026-09-27 | BUG-004~008 回归 verified(串行 pytest 62 passed、tsc 零错误,判据见 .scratch/regression-R2.md),迁移 ISSUES.md;回归抽查新发现 BUG-009(requirements cancel 端点权限协程未 await,既有隐患)入循环 | rd-fix 回归轮 |
| 2026-09-27 | 新增 R2.F3 修复 BUG-009(补 await 1 行 + 2 用例 Red→Green,4 文件串行 31 passed,RuntimeWarning 清零),verified 迁移 ISSUES.md;顺带发现 BUG-010(conftest 迁移回退未 await,低危测试基建)留 BUGS.md 待定夺 | rd-fix 循环 |
| 2026-09-27 | 新增 R4.F1/R4.F2 修复 BUG-011(四维删除操作 + 关联守卫);分析发现发布页「已部署」筛选用了不存在的状态值,登记 BUG-012 | 用户指令 |
| 2026-09-27 | BUG-011 回归 verified(串行 12 文件 80 passed、tsc 零错误、API 抽查 19/19、BUG-012 未触碰,见 .scratch/regression-R4.md),迁移 ISSUES.md;删除轮修复完成 | rd-fix 回归轮 |
| 2026-09-27 | 新增 R5.F1 修复 BUG-013(项目详情页需求列表编辑/删除,纯前端) | 用户指令 |
| 2026-09-27 | R5.F1 完成:抽取 RequirementEditDialog 共享组件(DimensionPage −291/+13 改 import,RequirementList +107),tsc 零错误、后端 14 passed、ui-check 含两页语义一致性;BUG-013 verified 迁移 ISSUES.md | rd-fix 循环 |
