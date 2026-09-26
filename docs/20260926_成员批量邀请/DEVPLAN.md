# 开发计划:项目成员批量邀请

> PRD:./PRD.md(已确认 2026-09-26)
> 创建日期:2026-09-26
> 状态:**已确认**(人工核对通过,待确认清单为空)

## 需求概述

项目详情「成员」页邀请改造:原手机号单个邀请**替换**为选择式——owner 从平台用户列表(候选接口,分页+搜索)多选用户、统一指定角色、**整体事务**批量加入(任一失败整批拒绝并列原因);成功后同步 GitLab 仓库成员。

## 技术约定

- 后端:FastAPI + SQLAlchemy 2 async,统一响应三键,角色校验 `require_project_role`/`require_owner`(超管经 get_project_role 旁路);审计沿用 project_member.add
- 前端:api/projects.ts membersApi + react-query hooks 体系;ui 组件自研(新增 Checkbox);design.md 按钮规范(Plus 图标)
- 数据库:**无表结构变更**(复用 project_members 唯一约束 uq_project_member_user 兜底)

## 当前进度

**当前进度: 2/3 (67%) - R2 已完成,接下来 R3**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 候选用户列表接口 | M1 后端 | ✅ | ./DEVPLAN/R1.md |
| R2 | 批量邀请接口(整体事务) | M1 后端 | ✅ | ./DEVPLAN/R2.md |
| R3 | 选择式邀请 Dialog(替换手机号直添) | M2 前端 | ⬜ | ./DEVPLAN/R3.md |

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| M1 后端 | R1, R2 | - | 0.5d | 1 |
| M2 前端 | R3 | R1R2 契约 | 0.5d | 2 |

## 业务旅程(跨需求点)

| 旅程 | 链路(需求点顺序) | 关键数据传导 |
|---|---|---|
| J1 批量邀请全流程 | R1 候选浏览 → R3 选择提交 → R2 入库+GitLab 同步 | 候选列表 is_member 标记禁选;批量事务成功后成员列表与 GitLab 同步刷新 |

## 范围外

- 手机号直添入口(随替换取消)、owner 批量授予、跨页全选、用户注册引导

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-26 | 初始版本;PRD 四项确认(替换/统一角色/整体事务/停用禁选) | 人工拍板 |
| 2026-09-26 | R1 完成并提交:is_member 并入 project.owner_id 兜底为合理扩展(与 D16 get_project_role owner 直判口径一致,防 owner 被低角色重插脏行);轻量审计通过(读端点无资损逻辑,未走 code-review 双轴,定级留痕);非阻塞跟进 2 条移交 R2 QA 顺带补:owner 自身行 is_member=True 断言、viewer 403 显式用例;QA 8/8 GREEN(Red 不可观测系 QA∥实现并行落盘,测试独立按分片契约编写);8 条 teardown ERROR 为外部锁噪声(trx 214745) | rd-dev 决策留痕 |
| 2026-09-27 | R2 契约裁决:「含重复 user_ids」按 PRD.md:46+完成判据=整批 400/12008,推翻分片「静默去重」行为规格行(R2.md 已修正留痕),实现同步反转 | rd-dev 决策留痕 |
| 2026-09-27 | R2 完成并提交:ErrCode 12006-12009;预检/插入分离同事务;IntegrityError→回滚 400/12009;QA 22 passed/0 failed(12 批量+10 candidates,跨三轮拼图,ERROR 级均为 teardown 1213 锁噪声);深度审计 Pass(五维达标 Low×7):①容量文案未列超出人数②GitLab 同步实为提交前执行(语义成立,与「提交后」措辞不符)③role 枚举违反 422 非字面 400(全站 pydantic 惯例)④测试 #12 回滚断言共享 session 下空真——均不阻塞,留 rd-check;工作树混有并行会话 R35.F1 WIP,未走全量 code-review 双轴,rd-check 兜底 | rd-dev 决策留痕 |
