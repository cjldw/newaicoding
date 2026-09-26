# 开发计划:需求关联用户/评审通知 + 原型链接/交付时间(合并)

> PRD:./PRD.md(需求关联用户通知,已确认)+ ../20260926_需求原型链接与交付时间/PRD.md(已确认)
> 创建日期:2026-09-26
> 状态:**已确认**(2026-09-26 人工核对通过,含 R7 补录)

## 需求概述

两个已确认 PRD 合并开发:需求实体新增**关联用户**(多选项目成员)、**原型链接(多条)**、**交付时间(date)** 三组字段;评审通过向关联用户发站内通知;交付时间临近/逾期定时提醒(每日巡检);工作台口径升级为「与我相关」(用户指令,骨架保留)。

**PRD 映射**:DEVPLAN R1-R3 = 关联用户通知 PRD 的 R1-R3;DEVPLAN R4-R6 = 原型链接 PRD 的 R1-R3。

## 技术约定(调研已定,按此实现)

- 存储:related_user_ids/prototype_links → **JSON 列**(对齐 knowledge_entry.tags/source_links 先例);delivery_date → **独立 DATE 列**(巡检 WHERE + 列表排序需索引命中)
- 通知:`notification_service.send_notification`(首个业务调用方);type=review_approved 枚举已存在,新增 req_delivery_reminder(MySQL ENUM 改表→DEPLOY.md)
- 调度:main.py lifespan 仿 _runner_offline_sweep 挂每日巡检;last_run_date 存 platform_settings(key 白名单加 req_delivery_reminder_last_date);「今天」= UTC naive +8h(GMT+8)
- 权限:创建/编辑均 editor+(:81,121 现口径);详情查看 viewer;R2 编辑沿用 PATCH
- 顺带修复:api/requirements.py 缺 ErrCode import 的潜伏 NameError(调研发现,:124/:227 使用)

## 当前进度

**当前进度: 1/7 (14%) - R1 已完成,R4 开发中**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 关联用户字段(创建+存储) | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R1.md |
| R2 | 关联用户详情可编辑 | M1 后端+M2 前端 | ⬜ | ./DEVPLAN/R2.md |
| R3 | 评审通过站内通知 | M1 后端 | ⬜ | ./DEVPLAN/R3.md |
| R4 | 原型链接字段 | M1 后端+M2 前端 | 🔄 | ./DEVPLAN/R4.md |
| R5 | 交付时间字段+逾期标记 | M1 后端+M2 前端 | ⬜ | ./DEVPLAN/R5.md |
| R6 | 交付提醒(每日巡检) | M1 后端 | ⬜ | ./DEVPLAN/R6.md |
| R7 | 工作台「与我相关」口径升级 | M1 后端+M2 前端 | ⬜ | ./DEVPLAN/R7.md |

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| M1 后端(迁移+字段+通知+巡检) | R1R2R3R4R5R6 后端面 | - | 1d | 1 |
| M2 前端(表单/详情/列表) | R1R2R4R5 前端面 | M1 契约 | 1d | 2 |

建议开发顺序:R1→R4→R5(三字段同迁同表单)→R2→R3→R6。

## 业务旅程(跨需求点)

| 旅程 | 链路 | 关键数据传导 |
|---|---|---|
| J1 创建带干系人的需求 | R1+R4+R5 创建表单 → 保存 | 三字段同请求落库 |
| J2 评审通过通知 | R2 编辑名单 → R3 通过触发 | 名单按当次值,排除操作人 |
| J3 交付提醒 | R5 设置日期 → R6 每日巡检 → 通知 R1 名单 | last_run_date 防重入;终态跳过 |

## 范围外

- 钉钉通道、链接有效性检测、工作日计算、逐日重复提醒、存量补录、跨页全选(同前两 PRD)

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-26 | 初始版本(两 PRD 合并,存储/调度/通知接线按调研拍板) | rd-plan 调研 |
| 2026-09-26 | 新增 R7 工作台「与我相关」口径升级(created_by → 关联用户∪created_by,任务加需求传导;骨架保留不按角色分叉) | 用户指令 + 方案确认 |
| 2026-09-26 | 人工核对通过(R1-R7 全确认;R4 链接整组 400 口径确认;ErrCode 顺带修复列入 R1) | 用户确认 |
| 2026-09-26 | 技术决策:alembic 迁移在 R1 一次建齐三字段列(related_user_ids/prototype_links/delivery_date),R4/R5 直接使用——按 DEVPLAN「三字段同迁」建议,避免三次 ALTER | rd-dev 决策留痕 |
