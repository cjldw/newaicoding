# 设计稿落地:任务容器未启动置灰引导

> 创建日期:2026-09-29
> 状态:进行中

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| TaskDetail 容器门卫(置灰+启动弹框) | ✅ | (无设计稿,需求直述) | 2026-09-29 浏览器核对 a-e 全通过 |

## 核对记录(2026-09-29,浏览器实测,超管登录)

| 断言 | 结果 |
|---|---|
| a. 终态任务门卫:全页遮罩+弹框「任务容器未启动,是否启动容器」+ 启动/暂不 | ✅(cancelled 任务 9b13f31d,report/01-gate-dialog.png) |
| b. 「启动」→ retry → 状态 running、遮罩自动撤;再「停止任务」回终态 | ✅(02 中间态转瞬未截,03-running-released.png) |
| c. 「暂不」全撤 + 同 tab 刷新不重现(sessionStorage 本 tab 会话语义) | ✅(04-dismissed.png) |
| d. pending 任务:门卫出现、「启动」disabled(后端 retry 不收 pending) | ✅(b0408f29,05-pending-disabled.png) |
| e. running 任务无门卫 | ✅(279938f7;e17584d3 已被超时清扫转 timeout,门卫正确出现) |

## 环境留痕(本轮核对附带)

- 上一轮核对 agent 误自注册测试账号(13899990001)/建空项目(f2cdc006),本轮已清理:账号禁用(无 DELETE 端点)、项目软删
- 顺带查出真实环境 bug **BUG-075**(创建需求 500 = 缺 tzdata),另行记录处理
- 实际测试任务 9b13f31d 经「启动→停止」往返,最终回终态

## 需求来源

- 用户口述:任务页面(需求打磨/任务开发/测试/发布等)涉及 container 服务的,只要 container 没有启动,页面置灰并弹框「任务容器未启动,是否启动容器」;是→调用容器启动接口;否→关闭弹框

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/pages/tasks/TaskDetail.tsx | 修改 | 容器门卫状态机 + 遮罩 + 弹框 |

## 交互规格

- 判定:task 数据就绪后 `display_status ?? status` ∉ {running, starting} → 门卫生效
- 门卫 UI:全页置灰遮罩(fixed,复用 .page-blocking-overlay 同族)+ ui/Dialog 弹框,文案「任务容器未启动,是否启动容器」,按钮「启动」/「暂不」
- 是:调启动接口(现契约=POST /tasks/{id}/retry,R37.F3 拉起口径;pending 态启动路由实现时核实)→ 弹框关,遮罩转「容器启动中…」loading,轮询到 running 自动撤
- 否:弹框+遮罩全撤,可浏览不可操作;sessionStorage 按 taskId 记跳过标记,本会话不重弹(刷新/重进再弹)
- 与「停止任务」遮罩(stopRequested)互斥:running 才有停止按钮,非 running 才有门卫,状态天然不相交
- starting(启动中)不弹框,遮罩直接显示「容器启动中…」直至 running(与 BUG-063/R3.F2 徽章口径一致)

## 边界口径(设计决定,登记)

- 终态(done/cancelled/failed/timeout)与 pending 统一门卫,不特判
- 「启动」映射 retry;后端契约不支持的态(如部分类型 done)由接口报错 toast 透出,前端不 mock

## 占位与待办

- pending 态如无独立启动路由:复用 retry;若 retry 不收 pending(后端报错),记待开发支持清单

## 待开发支持清单

- pending 态「启动」按钮:后端 retry_task 只收 failed/cancelled/timeout(pending 会报 TASK_REQ_STATUS_INVALID),前端已做 disabled + toast 提示「排队任务等待调度」,待后端支持 pending 态独立启动路由

## F1 修正:弹框按钮样式统一(2026-09-29 用户走查反馈)

- **问题**:门卫弹框「启动」「暂不」两按钮都是灰色——根因是按钮类名写成了不存在的 `btn-primary`,回退成灰底 `.btn`
- **修正**:TaskDetail.tsx L1255-1272「启动」→ `btn btn-pri`(站点主按钮,--primary 实底白字),「暂不」→ `btn`(次按钮);disabled 态复用既有 `opacity:.45 + not-allowed`
- **核对**:两按钮 computed style 与站内 `.btn-pri` 一致、disabled 抽验通过,截图 `report/06-button-style.png`
