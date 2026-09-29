# 设计稿落地:对话框输入框多行输入

> 创建日期:2026-09-29
> 状态:完成

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| TaskChat 输入框多行输入 | ✅ | (无设计稿,需求直述) | 2026-09-29 浏览器核对 a-d 全通过 |
| F2:输入框固定回原单行高度 | ✅ | (走查反馈) | 自增高过高,删 R35 effect 定高 34px 内部滚动 |

## 需求来源

- 用户口述需求(无设计稿):AI 对话框的输入框支持多行输入,Ctrl+Enter 实现换行逻辑

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/components/TaskChat.tsx | 修改 | 单行 input → 自增高 textarea;键位逻辑重排;IME 保护 |
| docs/20260929_对话框输入框多行输入/DESIGNLOG.md | 新增 | 本档案 |

## 交互规格

- Enter(无修饰键):发送(保持现状)
- **Ctrl+Enter / Cmd+Enter:光标处插入换行,不发送**(本次需求核心)
- Shift+Enter:换行(textarea 原生行为,顺带修复原单行 input 下失效的问题)
- 中文输入法组合中:Enter 不触发发送(isComposing 保护,textarea 下必须补)
- @ 文件 / / Skill / /mcp 补全下拉的键盘导航逻辑保持不变,优先级最高
- 输入框 1 行起步,随内容自增高,约 6 行后内部滚动;发送清空后高度复位

## 占位与待办

- 无(纯前端交互改动,发送链路不变)

## 待开发支持清单

- 无

## 核对记录(2026-09-29,浏览器实测,后端 8000 / 前端 5173 已登录)

| 断言 | 结果 |
|---|---|
| a. textarea + placeholder 含「Enter 发送,Ctrl+Enter 换行」 | ✅ |
| b. Ctrl+Enter 光标处插 `\n` 不发送;高度 34→55px 自增高 | ✅ |
| c. Shift+Enter 原生换行 | ✅ |
| d. Enter 触发发送(输入框清空 + 气泡出现) | ✅ |

- 截图:`report/02-multiline-ctrl-enter.png`(多行输入)、`report/01-after-send.png`(发送后)
- F2 复核(2026-09-29):定高 34px、多行内部滚动、键位回归全通过,截图 `report/03-fixed-height.png`
- 顺带发现预存 tsc 报错:`TaskChat.tsx` L253 `evt.confirmId` vs 类型字段 `confirm_id`,已记 `docs/20260927_AI对话框气泡优化/BUGS.md` BUG-UI-093(open,非本次引入)
