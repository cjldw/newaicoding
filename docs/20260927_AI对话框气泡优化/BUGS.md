# BUGS.md — 活跃问题清单

> 项目:AI 对话框消息气泡优化(R34)| 更新:2026-09-27
> 历史:R34 首轮静态核对 4 条(BUG-UI-086~089)已 fixed,见 git 历史/ISSUES。
> 核对方式:静态代码核对;浏览器走查未执行(环境无 Playwright 工具)。

### BUG-UI-090:「停止生成」按钮仅在流式增量已开始后才出现,长任务排队/执行阶段无法停止

- **严重程度**:中
- **关联页面**:任务详情页 AI 对话框(TaskChat.tsx L716-731)
- **问题描述**:停止按钮渲染条件是 `{streamText && <button class="chat-stop">}`,即首个 `chat_delta` 到达前(thinking 阶段、后端同步执行最长 10 分钟)整个 pending 期间没有停止入口;用户报告「对话框没有停止操作」。且停止仅是前端展示层中止(stoppedRef),后端任务继续跑完。
- **建议方案**:① 停止按钮条件放宽为整个 `sendMut.isPending` 期间常显;② 真取消需后端支持(WS cancel / 任务 abort),列待开发支持。
- **状态**:fixed(前端部分) — 2026-09-27 停止按钮改为整个 `sendMut.isPending` 期间常显(TaskChat.tsx),点击行为不变;后端真取消待契约(R34.F1 挂起)

### BUG-UI-091:AI 返回内容需要用户确认时,页面无确认交互通道

- **严重程度**:高
- **关联页面**:任务详情页 AI 对话框(TaskChat.tsx)
- **问题描述**:claude CLI 执行中遇到权限确认/二选一询问(如「是否允许写入文件 y/N」)时,对话内容里出现确认请求,但页面没有确认按钮或交互通道,任务卡在等待输入。当前交互链路:WS 事件(chat_delta/chat_done)+ POST 同步等待,无「确认请求」事件类型与应答接口。
- **建议方案**:需要后端定义确认交互协议(事件类型 + 应答接口);前端收到确认请求后渲染「允许/拒绝」按钮(或选项列表),点击应答。前后端契约待设计——**先转 rd-plan 补规格**。
- **状态**:open(规格缺口 → 分流 rd-plan)

### BUG-UI-092:对话框不支持项目模型切换

- **严重程度**:中
- **关联页面**:任务详情页 AI 对话框(TaskChat.tsx)
- **问题描述**:项目设置已有多模型配置(R13,`modelConfigsApi`:`GET /projects/{id}/model-configs`,含 name/model/is_default/enabled),但对话框没有切换入口,发送请求也不携带模型选择——用户无法按消息/按会话切换模型。
- **建议方案**:① 输入区加模型切换下拉(项目已启用配置列表,默认选中 is_default 项);② 发送接口需支持携带 config_id——**现 `POST /tasks/{id}/messages` 是否支持待确认,不支持则需后端加字段**(待开发支持);③ 会话级记忆选择(组件 state 即可,刷新回默认)。
- **状态**:fixed(前端部分) — 2026-09-27 输入区附件按钮旁加模型切换下拉(启用配置,默认选 is_default,组件 state 记忆);`sendTaskMessage` 请求体携带 config_id(后端消费待契约,R34.F2 占位)

### BUG-UI-093:确认卡事件字段命名不一致,`evt.confirmId` 类型错误(tsc 预存报错)

- **严重程度**:一般(类型层,不影响运行时)
- **关联页面**:任务详情页 AI 对话框(TaskChat.tsx L253)
- **问题描述**:`ChatConfirmResolvedEvent` 类型字段为 `confirm_id`(snake_case),代码里访问 `evt.confirmId`(camelCase),`npx tsc -b` 持续报 TS2551。2026-09-29 多行输入框核对时发现,经 stash 本次改动复测确认为预存问题,非新引入。
- **建议方案**:统一改为 `evt.confirm_id`(与类型定义一致);或类型定义补 camelCase 映射。属确认卡交互(BUG-UI-091)范畴,修复时一并过。
- **状态**:open(预存,2026-09-29 记录)
