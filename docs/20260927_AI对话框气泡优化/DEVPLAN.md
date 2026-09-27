# 开发计划:AI 对话框消息气泡优化

> 创建:2026-09-27(rd-fix 从 BUGS.md 转化)
> 当前进度:R34.F1/F2 前端已修(🔄 后端契约已写实待实施);R34.F3 规格已确认,可进 rd-dev
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
| R34.F1 | 修复 BUG-UI-090 停止操作(前端常显 + 后端真取消) | - | 🔄(前端已修,待后端契约收尾) | ./DEVPLAN/R34.F1.md |
| R34.F2 | 修复 BUG-UI-092 模型切换(前端切换器先行,入参待后端) | - | 🔄(前端已修,待后端契约收尾) | ./DEVPLAN/R34.F2.md |
| R34.F3 | BUG-UI-091 确认交互(规格已确认:permission-prompt-tool 实证+降级白名单/5min 超时/两档/不审计) | - | ⬜ | ./DEVPLAN/R34.F3.md |

## 变更记录

| 日期 | 变更 | 来源 |
|---|---|---|
| 2026-09-27 | 新增 R34.F1/F2/F3 修复 BUG-UI-090/092/091 | 用户报告(rd-fix) |
| 2026-09-27 | R34.F1/R34.F2 前端部分实施完成(停止按钮常显;模型切换下拉 + config_id 占位),后端契约收尾待开发 | rd-fix |
| 2026-09-27 | 调研落 .scratch/fix-analysis.md(5 问);R34.F1/F2 后端契约写实(取消=runner exec_tool_cancel+pkill;模型=4 层加 config_id+--model flag+越权校验);R34.F3 规格补全(chat_confirm_request 事件 + POST confirm,4 项待拍板) | rd-plan |
| 2026-09-27 | 全部确认:R34.F1/F2 自动确认(依据充分),R34.F3 四项拍板(实证+降级路径/5min/两档/不审计)——状态已确认,可进 rd-dev | rd-plan |
