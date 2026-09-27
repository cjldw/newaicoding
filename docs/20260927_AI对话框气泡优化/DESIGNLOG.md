# 设计稿落地:AI 对话框消息气泡优化

> 创建日期:2026-09-27
> 状态:完成(8 区块全 ✅;静态核对 15 组+头像 6 项全通过,4 条偏差 fixed;浏览器走查未执行,见 BUGS.md 头注)
> 分支:main(当前与目标均为 main)
> 范围:仅 `frontend/` 内;无后端改动、无新依赖(复用 `utils/markdown.ts`)

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| 消息气泡视觉层级 | ✅ | .scratch/design-spec/气泡视觉.md | 宽度 85%/92%、px-4 py-3、AI 左 3px 强调边、分层阴影 |
| 消息元信息(时间戳+复制) | ✅ | .scratch/design-spec/气泡元信息.md | HH:MM 常显;hover 操作栏含复制(Copy→Check 1.5s) |
| Markdown 渲染升级 | ✅ | .scratch/design-spec/气泡markdown.md | 复用 renderMarkdown+useMemo;⟦@⟧ 占位符保留下载(事件委托) |
| 流式体验(光标+停止) | ✅ | .scratch/design-spec/气泡流式.md | chat-cursor-dot 橙色呼吸;停止=stoppedRef 闸阀(占位,服务端继续) |
| 气泡操作栏 | ✅ | .scratch/design-spec/气泡操作栏.md | 复制/重新生成(仅末条 AI)/引用回复;.chat-row:hover 热区 |
| 空态与错误态 | ✅ | .scratch/design-spec/气泡状态.md | 3 个 chat-suggest 快捷指令;失败红描边+重试(isPending 守卫) |
| 补全键盘导航+skill 引用格式 | ✅ | .scratch/design-spec/补全键盘导航.md | ↑↓ 循环+Enter 选中+scrollIntoView;selectSC 插入 /skill名 |
| 头像上移+用户头像 | ✅ | .scratch/design-spec/头像布局.md | .chat-head 20px 头像+昵称在气泡上方;Avatar 组件;多用户 sender 占位待后端 |

## 设计稿来源

- 无外部设计稿;以现行实现 `frontend/src/components/TaskChat.tsx` + `globals.css` chat-bubble 块为基线,按 2026-09-27 评审建议清单落地。

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/components/TaskChat.tsx | 修改 | R34 全区块:markdown 渲染、meta/操作栏、流式停止、空态/错误态、键盘导航、/skill 插入 |
| frontend/src/styles/globals.css | 修改 | R34 未分层块追加;旧 .chat-cursor 竖条删除改 .chat-cursor-dot |

## 核对记录

- 静态核对 15 组规范要点:13 组通过,4 条偏差 BUG-UI-086~089 全部 fixed(见 BUGS.md)
- 头像布局复核(2026-09-27 第二轮):6/6 项通过,0 新增 BUG,上一轮 4 条修复无回归
- 浏览器走查未执行(核对环境无 Playwright 工具);建议 dev 环境人工过一遍亮/暗主题
- `tsc -b --noEmit` 0 错误;`vite build` 通过

## 设计规范要点

(见各规范文件;关键值落 `.scratch/design-spec/*.md`,实现唯一依据)

## 占位与待办

- 重新生成:复用现有「发送」链路(把上一条用户消息重发),无新接口。
- 消息反馈(👍/👎):**待后端** `POST /tasks/{id}/messages/{mid}/feedback`,本期不做。
- 流式停止:当前 `useTaskChatStream` 无 abort 能力,**前端只做展示层中止**(清 streamText/thinking),服务端任务仍跑完——标注「占位,待后端支持取消」。

## 待开发支持清单

| 项 | 说明 | 交接 |
|---|---|---|
| 消息反馈接口 | 👍/👎 落库 | rd-plan/rd-dev |
| 流式取消 | WS/任务侧支持 abort | rd-plan/rd-dev |
| skill 引用格式 @→/ | 前端已改插入/显示为 /skill 名;需确认 claude CLI 侧解析兼容(@skill 为 CLI 原生格式) | rd-plan/rd-dev |
| 消息 sender 字段 | TaskMessage 增加 sender:{user_id,nickname,avatar_url},支撑多用户对话逐人显示头像 | rd-plan/rd-dev |
