# 开发计划:AI 对话框消息气泡优化

> 创建:2026-09-27(rd-fix 从 BUGS.md 转化)
> 当前进度:2/3 (67%) - R34.F1 ✅(消息级取消全链路);下一个 R34.F3(AI 确认交互)
> 状态:已确认(2026-09-27,待确认清单为空)

## 需求概述

AI 对话框三项增强:消息级停止(R34.F1)、模型切换(R34.F2)、AI 确认交互(R34.F3)。前端部分已于 rd-fix 轮完成;本计划承载后端契约与跨层实施方案。

## 技术约定

- 后端 FastAPI 分层:api → service → claude_service → runner_service →(自建 WS)→ runner(容器内 claude CLI)
- WS 事件:TaskEventRegistry 内存广播任意 dict,新增事件无注册表,3 处接线(后端 broadcast / tasks.ts 分支 / TaskChat UI)
- 前端:React 18 + react-query,api 层 frontend/src/api/tasks.ts,组件 TaskChat.tsx

## 进度表

| 编号 | 内容 | 负责人 | 状态 | 详情 |
|---|---|---|---|---|
| R34.F1 | 修复 BUG-UI-090 停止操作(前端常显 + 后端真取消) | - | ✅ | ./DEVPLAN/R34.F1.md |
| R34.F2 | 修复 BUG-UI-092 模型切换(前端切换器+后端 4 层契约) | - | ✅ | ./DEVPLAN/R34.F2.md |
| R34.F3 | BUG-UI-091 确认交互(规格已确认:permission-prompt-tool 实证+降级白名单/5min 超时/两档/不审计) | - | ⬜ | ./DEVPLAN/R34.F3.md |

## 变更记录

| 日期 | 变更 | 来源 |
|---|---|---|
| 2026-09-27 | 新增 R34.F1/F2/F3 修复 BUG-UI-090/092/091 | 用户报告(rd-fix) |
| 2026-09-27 | R34.F1/R34.F2 前端部分实施完成(停止按钮常显;模型切换下拉 + config_id 占位),后端契约收尾待开发 | rd-fix |
| 2026-09-27 | 调研落 .scratch/fix-analysis.md(5 问);R34.F1/F2 后端契约写实(取消=runner exec_tool_cancel+pkill;模型=4 层加 config_id+--model flag+越权校验);R34.F3 规格补全(chat_confirm_request 事件 + POST confirm,4 项待拍板) | rd-plan |
| 2026-09-27 | 全部确认:R34.F1/F2 自动确认(依据充分),R34.F3 四项拍板(实证+降级路径/5min/两档/不审计)——状态已确认,可进 rd-dev | rd-plan |
| 2026-09-27 | R34.F2 完成:QA 红测试 4 用例 → 后端 4 层契约转绿(越权 1901)→ 审计 0 阻塞;提交 7eb7a0a+3b19a88。观察项:1901 未带 403、会话 config_id 不校验 enabled、runner --model 无单测 | rd-dev |
| 2026-09-27 | R34.F1 完成:runner exec_tool_cancel(pkill claude)+ POST /tasks/{id}/messages/cancel(editor/幂等)+ cancel_stream_request 本地结算,前端停止按钮接线;QA 72+19 全绿,审计通过(4 条非阻塞观察项)。决策:①契约按 QA 拍板(editor 档、幂等 cancelled=False、req_id 原样追踪);②工作区多需求混合,按 hunk 分割提交(tasks.py 剔除 R4.F2 DELETE、tasks.ts 剔除 deleteTask),tsc 残留 useDeleteTask 报错随 R4.F2 提交自愈 | rd-dev |
