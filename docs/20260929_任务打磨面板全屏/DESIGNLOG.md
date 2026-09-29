# 设计稿落地:任务打磨面板全屏

> 创建日期:2026-09-29
> 状态:进行中

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| PRD 草稿面板全屏 | ✅ | (无设计稿,需求直述;复用编辑器全屏机制) | 2026-09-29 浏览器核对通过 |
| 工作区面板全屏 | ✅ | 同上 | 同上(工作区 pane 新增 card-foot) |

## 核对记录(2026-09-29,浏览器实测,/tasks/e17584d3… 超管登录)

- 两 Tab 各有独立全屏按钮(card-foot 右侧,与编辑器先例同位)✅
- 点击 → pane `fixed inset-0 z-[60]` 覆盖全视口(8px 内边距),按钮变「退出全屏」;按钮/Esc 双路退出,无 fixed 类残留 ✅
- 截图:`report/01-prd-fullscreen.png`、`report/02-files-fullscreen.png`、`report/03-normal.png`

## 需求来源

- 用户口述:任务打磨页面(/tasks/{id},requirement 型)「PRD 草稿」与「工作区」支持全屏操作
- 页面实况:全屏基建已有(fullscreen state 'chat'|'term'|'editor'|null + fixed 覆盖层不重挂载 + Esc 退出 + 编辑器 Maximize2/Minimize2 按钮先例),本需求 = 接入 prd/files 两 pane

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/pages/tasks/TaskDetail.tsx | 修改 | fullscreen 扩 'prd'/'files';两 pane 头部加切换按钮(照编辑器先例) |

## 交互规格

- 各 pane 头部(或 card-foot 操作区)全屏按钮:进入 → 该 pane fixed inset-0 覆盖层(不重挂载),按钮变 Minimize2「退出全屏」
- 再点按钮或 Esc 退出;与 chat/term/editor 全屏互斥(同一 state)
- requirement 型左右已对调(BUG-UI-081:PRD/工作区在右栏 384px),全屏解决窄栏编辑体验

## 占位与待办

- 无

## 待开发支持清单

- 无
