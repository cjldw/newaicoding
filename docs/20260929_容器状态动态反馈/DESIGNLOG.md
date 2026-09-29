# 设计稿落地:容器状态动态反馈(启动 loading + 时间计数)

> 创建日期:2026-09-29
> 状态:进行中

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| TaskDetail 标题旁状态徽章动态化 | 🔄 | (无设计稿,需求直述) | 打磨/开发等全任务型共用头部 |

## 需求来源

- 用户口述:任务打磨、任务开发页面,容器启动状态(标题旁边的状态)做动态 loading,并加上时间显示有反馈的样式

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/pages/tasks/TaskDetail.tsx | 修改 | 徽章旁时间反馈 + 启动态 spinner;1s ticker |

## 交互规格

- 数据源:`task.started_at`(已有字段);1s `setInterval` ticker(组件卸载/taskId 变化清理)
- `启动中`(display_status=starting):徽章前加 Loader2 `animate-spin`,徽章后时间「· Ns」——加载中+已等多久,双重反馈
- `运行中`(running):保留既有 pulse 圆点,徽章后「· Nm Ss」运行时长
- 时间格式:<60s → `Ns`;≥60s → `Nm Ss`;started_at 缺失(旧数据/未启动)不显示时间
- pending/done/cancelled 等其余状态徽章零变化
- `StatusBadge` 共享组件不动 → 项目/需求列表页零波及;时间 chip 用现有 muted/mono 类,必要时 globals.css 补一个语义类

## 占位与待办

- 无

## 待开发支持清单

- 无

## 核对记录(2026-09-29,浏览器实测,超管登录)

- **运行中计时** ✓:「运行中 · 533m19s → 533m37s」3s 递增、格式合规(830af6e6,当时唯一 running),截图 report/01-running-timer.png
- **启动中瞬态**:容器启动过快(<300ms),300ms×40 次采样未捕获画面;该态渲染路径与已实测的运行态 chip 同族(spinner+chip 条件渲染,代码在位),留痕不重复造景
- **终态无 chip** ✓(e17584d3 timeout,只读)
- **核对中修复实现 bug**:ticker 的 useState/useMemo/useEffect 原写在 `if (!task) return` 之后——违反 React hooks 规则,task 数据从无到有时会「Rendered more hooks」崩溃;已移到 early return 之前(核对 agent 修回,修后运行态实测兜底)
- 测试任务 9b13f31d 经「启动→停止」往返,终态收场
