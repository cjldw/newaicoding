# 设计稿落地:任务停止页面置灰

> 创建日期:2026-09-29
> 状态:进行中

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| 任务详情页「停止任务」全页置灰遮罩 | ✅(静态核对) | (无设计稿,需求直述) | 动态链路待有运行任务时复测(见核对记录) |

## 需求来源

- 用户口述(无设计稿):任务停止操作点击后,整个页面置灰,直到容器停止后消失

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/pages/tasks/TaskDetail.tsx | 修改 | 停止点击 → 全页遮罩;status 离开 running 撤销;接口报错撤销+toast |
| frontend/src/styles/globals.css | 视需要 | 遮罩样式(优先复用现有类) |

## 交互规格

- 触发:任务详情页「停止任务」(btn-danger,running 态)点击即置灰
- 遮罩:fixed 全视口半透明灰,拦截一切点击,含 spinner +「正在停止容器…」提示
- 消失条件:`useTaskDetail` 轮询(5s)到 status ≠ running(容器已停,任务转 cancelled 等终态)
- 异常:POST /tasks/{id}/stop 失败 → 立即撤遮罩并 toast 错误,不停留死灰
- 不改后端:POST 同步返回则遮罩即时消,异步则靠既有轮询

## 占位与待办

- 无

## 核对记录(2026-09-29)

**静态核对(通过)**——代码级 + computed style 全部就位:
- `.page-blocking-overlay`(globals.css):fixed / inset:0 / rgba(9,9,11,.5) / z-index:70 / 居中 flex / cursor:not-allowed / 子元素 pointer-events:none,实测覆盖全视口 2560×1249
- TaskDetail.tsx:`stopRequested`(L138)→ taskId 变化/卸载复位(L193-196)→ display_status 离开 running/starting 自动撤遮罩(L201-208)→ handleStopClick 含 onError 撤遮罩+提示(L288-299)→ 按钮 disabled 且文案「停止中…」(L305-306)→ 遮罩 JSX Loader2+「正在停止容器…」(L717-722)

**动态链路(未验)**:dev 环境当前全项目任务列表 0 条,无运行中任务可点。复测口径:启动任一 dev 任务 → 详情页点「停止任务」→ 断言遮罩即现(截图)→ 容器停止(状态转已取消等)遮罩消失。

## 待开发支持清单

- 无
