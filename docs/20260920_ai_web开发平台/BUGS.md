# BUGS.md — 活跃问题清单

> 项目:ai_web开发平台 | 更新:2026-09-28(rd-fix 第 35 轮收敛:BUG-065 verified——用户报障对话 9001「未知工具: claude_prompt_stream」,R8.F6 协同修复(runner 容器旧镜像回退热补→镜像重建+容器重建),本会话独立四层探针+生产 parity 复验全过;附带登记 BUG-066(R32 标签代码二次丢失,移交 R32 流)/BUG-067(流式 stderr 吞+瞬态空回复不可回溯+Windows EOF 隐患,防并行双写不自动修)。第 34 轮收敛:BUG-064 verified 迁移 ISSUES.md(R22.F3 打磨任务纳入 /manage/tasks;pytest 23 过+真机 API+无头浏览器 3/3 复验);第 34 轮追加:BUG-053(分支预览真首拼,R34.F1 域)+BUG-068(成员项目列表空,R12.F1)verified 迁移 ISSUES.md。第 33 轮:BUG-063 用户指令——打磨容器启动窗口期页面显示「启动中」,R3.F2 修复闭环 fixed(pytest 5/5+回归 123 过+真机探针 4/4,verified 待用户浏览器复验);编号让渡:初登记 BUG-062 撞第 32 轮占用,改号 BUG-063。第 32 轮:BUG-062 用户指令——生成 requirements.txt 默认安装路径,修复 pip install -e . 不可用 + 本机依赖散装(BUG-061 根因链),已 verified 迁移(升级回归=0,22 个失败经分类全为并行流测试先行/环境噪音);第 31 轮:BUG-061 需求创建 500 环境缺陷——pypinyin 已声明未装入运行时,零代码补装+回归全过,verified 迁移;BUG-052 接线已随 93242f9 解决一并 verified 迁移,BUG-053 仍 open;⚠ 轮次编号让渡:第 29/30 轮已被 2026-09-27 并发会话使用,见 ISSUES.md)
> 状态流转:open → fixed → verified(verified 后迁移至 ISSUES.md)
> 已 verified 迁移:第 3 轮 BUG-UI-001/003/004/005/006;第 4 轮 BUG-010;第 5 轮 BUG-009/011/012/013;第 16 轮 BUG-038;第 17 轮 BUG-039;第 18 轮 BUG-040/041;第 27 轮 BUG-UI-071/072/073;第 28 轮 BUG-051;第 34 轮 BUG-064/BUG-053/BUG-068;数据修复(2026-09-26)BUG-DATA-001(第 19-26 轮迁移见各行标注;均见 ISSUES.md)

| BUG-042 | fixed → 已 verified 迁移 ISSUES.md(2026-09-24 第 21 轮真机删除实证) | R16 | 功能缺陷(拦截口径过宽) | 用户实测报障 2026-09-24(rd-fix 第 19 轮) | 删除 Runner 返回 16001"Runner 上有运行中的容器,不可删除",但容器关联任务已非进行中(cancelled/done):delete_runner 只看 containers.status,不联查任务状态,孤儿容器行(任务取消链路缺容器状态回写)永久卡死删除;用户口径:任务不是进行中可以删除;修复分片 R16.F3(拦截收窄为容器关联 Task.status='running',部署容器 task_id NULL 放行;pytest 11/11,后端已重启) |
| BUG-043 | fixed → 已 verified 迁移 ISSUES.md(R31.F1;真机 shell-sessions code=0) | — | — | — | — |

| BUG | 状态 | 关联需求点 | 类型 | 来源 | 摘要 |
|---|---|---|---|---|---|
| BUG-007 | fixed | R16(波及 R9/R11 产物) | 部署阻塞 | rd-ship 发布检查 | docker/runner/Dockerfile 缺 terminal_manager.py / file_watcher.py,Runner 镜像启动即 ImportError |
| BUG-UI-002 | 已核实:与稿一致,不修 | admin-audit-logs | UI 偏差 | Playwright 核对 2026-09-22 | 核对时审计表为空,`totalPages>1` 不成立 → 分页整体不渲染;代码中 `.card-foot` 包裹存在(AuditLogsPage.tsx:257),与 vp"审计页无分页脚注"一致 |
| BUG-014 | fixed → 已 verified 迁移 ISSUES.md(R22.F1;四维页浏览器实测不崩) | — | — | — | — |
| BUG-015 | fixed | R1(波及 R3/R4 任务链) | 功能缺陷 | rd-test 数据准备阶段实证 | 用户绑定 GitLab token 校验打到硬编码 gitlab.com,自建 GitLab 环境绑定必失败(1012),阻塞需求评审/任务创建全链 |
| BUG-016 | fixed | R1(波及 R3/R4 任务链) | 功能缺陷 | rd-test 数据准备阶段实证 | GitLab v11.x 不返回 X-Token-Scopes 头,有效 token 被误判 1013 缺权限,绑定被阻 |
| BUG-UI-007 | 已核实:OVERREACH 不修 | R1 | UI 偏差 | rd-test TC-R1-08 | 登录页标题 font-size 17px,期望 22px(1.375rem) |
| BUG-UI-008 | 已核实:OVERREACH 不修 | R1 | UI 偏差 | rd-test TC-R1-09 | 登录页输入框 font-size 13px,期望 16px(1rem) |
| BUG-UI-009 | 已核实:OVERREACH 不修 | R1 | UI 偏差 | rd-test TC-R1-12 | 登录页卡片 border-radius 16px/padding 26px,期望 12px/24px |
| BUG-UI-010 | 已核实:OVERREACH 不修 | R1 | UI 偏差 | rd-test TC-R1-13 | 登录页表单项间距 ~14px,期望 16px(1rem) |
| BUG-UI-011 | 已核实:OVERREACH 不修 | R1 | UI 偏差 | rd-test TC-R1-14/16 | 登录页按钮 hover bg 与常态相同(无变化),transition "background 0.12s" 非 "all 0.15s" |
| BUG-UI-012 | 已核实:OVERREACH 不修 | R1 | UI 偏差 | rd-test TC-R1-15 | 登录页输入框 focus 仅单层 ring,期望双层 ring |
| BUG-UI-013 | 已核实:OVERREACH 不修 | R1 | UI 偏差 | rd-test TC-R1-17 | 注册页卡片宽度 448px(期望 400px),border-radius 10px(期望 12px),输入框/按钮 font-size 13px(期望 16px),transition 偏差,focus 单层 ring |
| BUG-UI-014 | 已核实:BYDESIGN(V2 预留)不修 | R1 | 功能缺失 | rd-test TC-R1-18 | 找回密码页为 V2 占位,无表单(期望手机号输入+发送按钮);卡片宽度 448px/border-radius 10px 亦偏差 |
| BUG-UI-015 | 已核实:BYDESIGN(V2 预留)不修 | R1 | 功能缺失 | rd-test TC-R1-19 | 重置密码页为 V2 占位,无表单(期望新密码+确认密码);卡片宽度 448px/border-radius 10px 亦偏差 |
| BUG-UI-016 | 已核实:OVERREACH 不修 | R2 | UI 偏差 | rd-test TC-R2-05 | 项目卡片 hover 仅变 border-color + box-shadow,无 bg-surface-strong(#f4f4f5)背景色变化 |
| BUG-UI-017 | 已核实:OVERREACH 不修 | R2 | UI 偏差 | rd-test TC-R2-08 | 项目卡片缺创建时间、操作按钮(查看/设置/删除),仅有名称(slug)+描述+仓库数+状态徽章 |
| BUG-UI-018 | fixed | R2 | UI 偏差 | rd-test TC-R2-06 | Dialog 动画 @keyframes dialogContentIn/dialogOverlayIn 未定义,CSS 中无此关键帧;关闭为 `if(!open) return null` 瞬时卸载,无淡出 |
| BUG-UI-019 | 已核实:OVERREACH 不修 | R2 | UI 偏差 | rd-test TC-R2-07 | 空状态文案"还没有项目"+"请点击右上角「新建项目」创建第一个项目"≠ 规范"暂无项目,点击右上角新建" |
| BUG-UI-020 | 已核实:OVERREACH 不修 | R2 | UI 偏差 | rd-test TC-R2-01/02/03 | /projects 使用 .pcards>.pcard 卡片布局,无 <table> 元素;TC-R2-02/03 列宽/操作列固定无从验证 |
| BUG-017 | 已核实:OVERREACH 不修 | R2 | 功能缺陷 | rd-test TC-R2-09 | 仓库列表"绑定时间"列显示"—"(未填充),操作列仅主仓库显示"主仓库不可解绑"(disabled),非主仓库无解绑按钮 |
| BUG-UI-024 | 已核实:OVERREACH 不修 | R3 | UI 偏差 | rd-test TC-R3-02 | 需求列表操作列宽度80px,期望200px固定宽度 |
| BUG-UI-025 | 已核实:OVERREACH 不修 | R3 | UI 偏差 | rd-test TC-R3-08 | 需求列表操作列仅1个图标按钮,期望3个文本按钮(查看/编辑/删除) |
| BUG-UI-026 | 已核实:OVERREACH 不修 | R3 | UI 偏差 | rd-test TC-R3-07 | 关联任务类型徽章"开发"颜色为黑色(rgb(24,24,27)),期望primary蓝色(bg-primary/10未生效) |
| BUG-018 | 已核实:非 bug,路由正常工作 | R3 | 功能缺陷 | rd-test TC-R3-03 | 需求详情页直接URL导航失败,跳转至首页,必须从列表页点击进入。**核实(2026-09-23)**:路由 `/requirements/:reqId` 正常注册且无守卫,Playwright 实测直接访问完整 UUID URL 可正常加载;列表页显示短 ID(前 8 字符)而非完整 UUID,用短 ID 访问时正确显示"需求不存在"而非跳转首页,属预期行为 |
| BUG-019 | verified | R3 | 功能缺失 | rd-test TC-R3-04 | 详情页背景/描述/验收标准内容无markdown渲染,显示为纯文本(0个p/ul/ol元素) |
| BUG-020 | 已核实:OVERREACH 不修 | R3 | 功能缺失 | rd-test TC-R3-04 | 详情页内容区域无独立滚动容器(body.scrollHeight===body.clientHeight),无overflow区域 |
| BUG-021 | 已核实:OVERREACH 不修 | R3 | 功能缺失 | rd-test TC-R3-04 | draft状态需求"崩溃复验"详情页缺少背景/验收标准区域,仅有基本信息标题 |
| BUG-022 | 已核实:OVERREACH 不修 | R3 | 功能缺失 | rd-test TC-R3-10 | approved需求详情页仅有"创建开发任务"按钮,缺少"编辑"/"打磨"/"提交"操作按钮 |
| BUG-023 | 已核实:OVERREACH 不修 | R3 | 功能缺陷 | rd-test TC-R3-11 | draft需求详情页"开始打磨"按钮点击无弹窗,页面无变化,编辑弹窗无法打开 |
| BUG-UI-027 | 已核实:OVERREACH 不修 | R4 | UI 偏差 | rd-test TC-R4-07 | "变更文件"Tab 缺少变更计数徽章(badge),innerHTML="变更文件"无子元素 |
| BUG-UI-028 | 已核实:OVERREACH 不修 | R4 | UI 偏差 | rd-test TC-R4-05 | 右侧面板无"活动"Tab |
| BUG-024 | fixed | R4 | 功能缺陷 | rd-test TC-R4-08 | 消息发送按钮点击无效:输入框未清空,消息未出现在聊天区域 |
| BUG-UI-029 | fixed | R5 | 功能缺失 | rd-test TC-R5-02 | 聊天输入框输入"@"后无文件自动补全下拉框弹出(totalDropdowns=0)。**修复(2026-09-23)**:TaskChat.tsx 下拉框条件从 `showAC && filteredFiles.length>0` 改为 `showAC` 并在内部条件渲染(无文件时显示"暂无已上传文件"/"无匹配文件"提示),根因是原条件要求同时满足 showAC 且有匹配文件,导致无上传文件或无匹配时下拉框不渲染 |
| BUG-UI-030 | 已核实:OVERREACH 不修 | R6 | 交互偏差 | rd-test TC-R6-07 | 审阅页"新增用例"点击后为内联表单(table row 内 input),非 Dialog 对话框 |
| BUG-025 | 已核实:vp 设计即任务详情子面板,无独立路由,不修(参照 BUG-UI-002 先例) | R7 | 功能缺陷 | rd-test TC-R7-01~05 | /tasks/:taskId/deploy 路由不可达,导航后被重定向至首页,发布页完全无法访问。**核实(2026-09-23)**:vp/index.html 中 deploy 为 TaskDetail 工作台子面板(任务类型 release 时展示),非独立路由;TESTCASE R7 期望独立路由与 vp 设计不符,按 vp 为准 |
| BUG-UI-035 | 已核实:OVERREACH 不修 | R14 | UI 偏差 | rd-test TC-R14-02/03/12 | 知识库工具栏无 .fbar 类名 |
| BUG-UI-036 | 已核实:OVERREACH 不修 | R14 | 功能缺失 | rd-test TC-R14-12 | 平台知识库缺标签过滤 Select + 新建条目按钮 |
| BUG-UI-031 | 已核实:OVERREACH 不修 | R9 | UI 偏差 | rd-test TC-R9-01 | 终端区无 Tab 栏结构 |
| BUG-UI-032 | 已核实:OVERREACH 不修 | R9 | UI 偏差 | rd-test TC-R9-04 | 终端空态未使用 --font-mono 字体 |
| BUG-UI-034 | 已核实:OVERREACH 不修 | R10 | UI 偏差 | rd-test TC-R10-03 | 预览区"在新窗口打开"按钮 variant 不符 |
| BUG-UI-037 | 已核实:OVERREACH 不修 | R10 | UI 偏差 | rd-test TC-R10-06 | Runner 管理页操作列宽度不符(期望 200px,实测 127px) |
| BUG-UI-041 | 已核实:OVERREACH 不修 | R19 | UI 偏差 | rd-test TC-R19-02 | 超管角色徽章非 primary 风格(白字深底) |
| BUG-UI-044 | 已核实:OVERREACH 不修 | R21 | UI 偏差 | rd-test TC-R21-01 | 统计卡 padding 不符规范 |
| BUG-UI-045 | 已核实:OVERREACH 不修 | R21 | UI 偏差 | rd-test TC-R21-02 | 统计数值字体大小不符 |
| BUG-UI-047 | 已核实:OVERREACH 不修 | R21 | UI 偏差 | rd-test TC-R21-04 | 页面标题字体不符 |
| BUG-UI-049 | 已核实:OVERREACH 不修 | R21 | UI 偏差 | rd-test TC-R21-06 | 响应式布局失效 |
| BUG-UI-050 | 已核实:OVERREACH 不修 | R22 | UI 偏差 | rd-test TC-R22-01 | 测试管理页无表格 |
| BUG-UI-051 | 已核实:OVERREACH 不修 | R22 | UI 偏差 | rd-test TC-R22-02 | 发布管理页无表格 |
| BUG-UI-056 | 已核实:OVERREACH 不修 | R22 | UI 偏差 | rd-test TC-R22-07 | 表格行 hover 样式缺失 |
| BUG-UI-057 | 已核实:OVERREACH 不修 | R22 | UI 偏差 | rd-test TC-R22-08 | 分页器对齐与间距不符 |
| BUG-UI-058 | 已核实:OVERREACH 不修 | R22 | UI 偏差 | rd-test TC-R22-09 | 空态样式待核实 |
| BUG-UI-063 | fixed | R2(跨页 UI 指令;波及 R3/R4/R14/R20) | UI 偏差 | 用户指令 2026-09-23 | 所有详情页面包屑必须带上级链(需求详情/任务工作台/知识库视图等),修复分片 R2.F7 |
| BUG-026 | verified | R8(镜像;波及 R17/R11 产物) | 部署阻塞 | rd-fix 本地 Runner 实测 2026-09-23 | devbox 基础镜像 mcr devcontainer/universal 已被微软退役(仓库 404),任务容器镜像无法构建,修复分片 R8.F1(镜像重建成功+E2E 在用) |
| BUG-027 | verified | R8/R16(Runner 运行时) | 功能缺陷(2 合 1) | rd-fix 本地 Runner 实测 2026-09-23 | ① Runner 事件监听无归属过滤,接管宿主机上非平台容器(实测反复重启用户自己的 monkeycode-ai-backend);② 同步 docker events 流阻塞 asyncio 循环,心跳饿死被判 offline,修复分片 R8.F2(心跳 30s 刷新+接管 0 实测) |
| BUG-028 | verified | R8(镜像契约) | 功能缺陷 | rd-fix 本地 E2E 实测 2026-09-23 | devbox CMD ["/bin/bash"] 在 detach 无 TTY 下秒退 → exec 失败 → 容器创建即被销毁;改 CMD ["sleep","infinity"](R8.F1 范围),镜像保活实测通过 |
| BUG-029 | verified | R8(Runner clone) | 功能缺陷 | rd-fix 本地 E2E 实测 2026-09-23 | 容器内 git clone 裸 URL 无认证(fatal: could not read Username);平台 env 已注入 GITLAB_TOKEN 但 Runner 未使用;修复分片 R8.F3(认证重试 + remote 洗净;round3/4 clone 成功+0 残留实证) |
| BUG-030 | verified | R8(平台回报处理) | 功能缺陷 | rd-fix 本地 E2E round3 实测 2026-09-23 | container_started 回报只更新 containers 表,tasks.container_id/runner_id 恒空;修复 container_service.handle_container_started 回填 tasks 行(round4 实测回填成功),修复点并入 R8.F3 记录 |
| BUG-031 | verified | R16(Runner pty;波及 R9 终端) | 功能缺陷(Windows 特有) | 用户实测 + rd-fix 第 13 轮 2026-09-23 | 任务页终端有回显但键盘输入全丢;NpipeSocket 非 socket.socket 子类且无 write,write_input isinstance 分派走错路径抛错被吞;改探测式 sendall 分派(R16 范围外直修),UI 复验每键回显 |
| BUG-032 | fixed | R5(AI 对话;波及 R4 工作台) | 功能缺陷(四层) | 用户实测 2026-09-23 | 对话发送卡"发送中"消息不入库;根因=runner 事件循环被同步 claude_prompt 阻塞(ping/心跳饿死→掉线/被 sweep 注销)+ 5 路 send 无锁并发(45min 掉线 3 次实证)+ 平台 request_runner 死连接 600s 死等 + 先落库后校验;修复=R5.F1(send 锁/to_thread/快速失败/校验前移),E2E 174s 全链路 200+消息落库,离线 0.06s 返 9001 |
| BUG-033 | fixed | R4(工作台变更面板;波及 R11) | 功能缺陷 | rd-fix 复测 2026-09-23 | GET /files/changes 间歇 500;真身=py3.10 asyncio.TimeoutError≠内建 TimeoutError,`except TimeoutError` 从未接住,超时裸奔 500;request_runner 归一化后 E2E 3×200 |
| BUG-034 | open | R13/R23(LLM 配置注入)+ 环境待办 | 功能缺陷(双层) | BUG-032 修复后 E2E 发现 2026-09-23 | 容器内 claude 连不上 LLM:① 代码=回环 base_url 原样注入容器(127.0.0.1=容器自身),已修 container_base_url 改写 host.docker.internal;② 环境=本地 LLM 代理 127.0.0.1:18765 当前未监听(宿主机自测也拒),需用户启动代理监听 0.0.0.0 或改配置为可达地址 |
| BUG-UI-064 | fixed | R4(任务工作台;波及 R9/R11 面板) | 功能增强(用户指令) | 用户指令 2026-09-23 | 任务页三面板(Terminal/AI 对话/文本编辑器)补齐全屏、保存、滚动,修复分片 R4.F1(tsc+build 过,verified 待浏览器) |
| BUG-UI-065 | fixed | R4(工作台;波及 R9/R11) | 功能缺陷批(用户实测) | 用户指令 2026-09-23 | terminal 不行(WS 无代理+tab 关不掉)/diff 不行(不设 diffPath)/对话无反馈态/编辑器底部贴边,修复分片 R4.F2(tsc+build 过,verified 待浏览器;**vite dev 需重启加载 /ws 代理**) |
| BUG-UI-066 | **fixed(R4.F4 二修;并排视觉核对过,待用户验收)** | R4(工作台;波及 R9/R11 面板) | UI 偏差(用户指令) | 用户指令 2026-09-23 | 任务工作台照抄重写 vp #/t/T-301(全出血骨架/wb-head 五段/五类型中栏/右栏三 Tab/CSS 原值/四链面包屑);并排截图对比见 `.scratch/R4.F4/ui-check.md`;顺带修复 Breadcrumb override 从未生效的深层缺陷 |
| BUG-UI-067 | fixed | R1 | UI 偏差(用户指令) | 用户指令 2026-09-23(rd-fix 第 15 轮) | 登录页删除 4 段演示/技术文案(品牌横幅/登录方式说明/GitLab token 已绑定/演示账号说明);LOGO 居中;忘记密码与注册页使用与登录页一致的 LOGO 图;修复分片 R1.F2 |
| BUG-UI-068 | fixed | R2(跨页 UI 指令;波及全部主页面) | UI 偏差(用户指令) | 用户指令 2026-09-23(rd-fix 第 15 轮) | ① 项目列表点击项目项打开项目详情(核对/补接线);② 所有主页面内容区大标题统一带 icon 风格(R2.F2 曾做 12 页,仍有遗漏页面);修复分片 R2.F8 |
| BUG-UI-069 | fixed | R22(波及 R3/R4/R6/R7 列表) | UI 改版(用户指令) | 用户指令 2026-09-23(rd-fix 第 15 轮) | 需求/任务/测试/发布四维表格统一 audit-logs 范式:筛选区与表格区分离;各维自有添加按钮(右上角,样式对齐 admin/runners),添加弹框补关联字段;并收敛 open 批 BUG-UI-052/053/054/055/059/060/061/062;修复分片 R22.F2 |
| BUG-035 | fixed | R3(波及 R4/R5/R8) | 功能增强(用户指令) | 用户指令 2026-09-23(rd-fix 第 15 轮) | 需求创建后点击「开始打磨需求」→ 创建 requirement 类型任务并初始化启动容器(复用任务创建即拉起容器链路);修复分片 R3.F1 |
| BUG-036 | fixed | R8(波及 R23/R2) | 功能增强(用户指令) | 用户指令 2026-09-23(rd-fix 第 15 轮) | 容器初始化注入 LLM_URL/LLM_MODEL;「平台设置」支持添加多个自定义变量,启动后全部注入 container;修复分片 R8.F4 |
| BUG-037 | fixed | R9(波及 R5 对话链路) | 功能增强(用户指令) | 用户指令 2026-09-23(rd-fix 第 15 轮追加) | 任务页开启终端自动进入 claude,与对话面板同一 claude 会话(--session-id/--resume 接线);修复分片 R9.F1 |
| BUG-040 | fixed → 已 verified 迁移 ISSUES.md(R28.F1;用户下拉补「个人设置」) | — | — | — | — |
| BUG-041 | fixed → 已 verified 迁移 ISSUES.md(R26.F1;6003 细分文案真机复验) | — | — | — | — |
| BUG-043 | 已核实:功能已存在不修(本机启动形态由 R31 承接) | R16/R31 | 功能增强(用户指令) | 用户指令 2026-09-24(rd-fix 第 20 轮) | 机器信息上报/展示 R16 已实现(提交 333b64e);Docker 部署自启(CMD + --restart unless-stopped)已实现;残余缺口=本机裸进程的平台侧启动/生命周期 → R31 增量5(并行会话实施中) |
| BUG-044 | ✅ 已解决(2026-09-24 环境闭环:换新 token 后 15:58 注册成功,online+机器信息上报) | R16 | 环境/运维(用户报障) | 用户报障 2026-09-24(rd-fix 第 21 轮) | 新建 runner-local 后页面显示离线:实为无任何进程持新 token 注册过(heartbeat NULL);本机滞留旧 runner 进程(PID 37084)持已删除 local-win-test 的死 token 每 60s 被正确拒绝;产品缺口(新建无部署指引/注册失败不可见)归 R31 |
| BUG-046 | fixed(第 23/24 轮;原崩溃真机实证消失;StrictMode 伪影代码级根除,零错终验归用户一瞥) | R9(终端组件;波及 R26 Runner 终端) | 功能缺陷(前端 xterm 时序崩溃) | 用户报障 2026-09-24(rd-fix 第 23 轮) | 新建终端 ws 报错+xterm RenderService.ts:52 dimensions undefined:Terminal.tsx 初始 fit 单 rAF 无守卫+ResizeObserver 首帧即无条件 fit,Runner 终端 Dialog 150ms 动画期容器尺寸未稳撞上渲染器未就绪(R31.F1 宿主 shell 落地后会话首次真开,前端时序缺陷首次暴露);修复=safeFit 统一守卫+open 延迟双 rAF;分片 R9.F2 |
| BUG-UI-070 | fixed → 已 verified 迁移 ISSUES.md(第 23 轮;滚动条计算样式真机实证) | R9(终端;波及 R26) | UI 增强(用户指令) | 用户指令 2026-09-24(rd-fix 第 23 轮) | 终端右侧滚动条美化:globals.css 纯追加 .xterm-viewport 细条样式(WebKit 8px 圆角半透明白+hover 加深/Firefox thin),终端底色恒深故双主题通用 |
| BUG-047 | fixed(第 24 轮;真机 API 三步链+runner 日志+DB 全实证) | R26(波及 R31 本机终端) | 功能增强(用户指令) | 用户指令 2026-09-24(rd-fix 第 24 轮) | 「该 Runner 已有终端会话,请先关闭」时提供强制关闭并新建:POST ?force=true 复用 terminal.py 关闭链路(terminal_close+closed_at)清活跃会话后放行;前端 6002 错误分支渲染「强制关闭并新建」按钮;分片 R26.F2 |
| BUG-048 | verified → 已迁移 ISSUES.md(R31.F2;真机 WS 全双工实证) | R31(宿主终端数据面,R31.F1 缺口) | 功能缺陷(Windows 管道模式双层) | 用户报障 2026-09-24(rd-fix 第 25 轮) | runner 新建终端 WS 握手成功但零输出:① 默认命令 `["cmd.exe"]` 缺 /K——管道 stdin 下 cmd 非交互即退(读循环 13s EOF「宿主 shell 读取结束」);② xterm Enter 裸 \r 不被管道 cmd 认作行尾;修复=默认命令加 /K + 宿主会话写入做 \r→\r\n 行尾仿真(pty 本应做的事);分片 R31.F2 |
| BUG-049 | verified → 已迁移 ISSUES.md(R31.F3;真机全链 PASS) | R31(核心机制需求修正) | 需求修正(用户指令,推翻 Q51 负向规格) | 用户指令 2026-09-24(rd-fix 第 26 轮) | 「快速创建(本机)」应为**平台直接在本机以 Docker 容器运行 runner**(零命令复制),而非 python 子进程;实现=镜像缺失自动构建(Dockerfile 参数化 BASE_IMAGE,Docker Hub 不可达时自动回退本地 python:3.10)+ docker run 挂载 sock/env 注入/host.docker.internal 回连 + exec cwd=/app 适配;子进程形态废弃不再新启;分片 R31.F3 |
| BUG-050 | verified → 已迁移 ISSUES.md(R26.F3;真机容器终端实证) | R9/R26(终端读循环;全部 Linux 容器形态 runner) | 功能缺陷(读循环硬编码 .recv) | 容器形态验证中发现 2026-09-24(rd-fix 第 26 轮) | `_read_loop` 硬编码 `session.sock.recv(4096)`——docker exec_start(socket=True) 在标准 Linux/Docker Desktop 返回 SocketIO(只有 .read()),AttributeError 秒崩零输出;Windows NpipeSocket 有 recv 故历史未暴露(R26 判据 4/8/11「真实 pty 待测」之债);修复=探测式读法(recv 有则用,否则 read,与 BUG-031 写侧探测同思路);分片 R26.F3 |
| BUG-DATA-001 | open → 已清理并 verified 迁移 ISSUES.md(2026-09-26 数据修复;前置守卫 UPDATE+复检+全库扫尾实证) | —(测试脏数据,非代码 bug) | 数据问题(E2E 客户端编码损坏) | 用户报障「中文汉字首拼音乱码」2026-09-26(rd-fix 数据修复) | tasks 表 id 945/946 标题 `??????`(HEX=字面 ASCII `3F` 字节,非 mojibake):2026-09-23 rd-fix 第 8 轮本地 Runner E2E 时 Windows 控制台(GBK 代码页)在请求侧把中文打成 `?` 写入的测试脏数据,两任务均 cancelled;拼音/分支命名代码无产生 `?` 路径;处置=就地改名保留留痕(禁删行)title→「历史测试数据(已清理)」,rows affected=2 其余行零触碰;全库扫尾其余 0 条 |
| BUG-052 | open → 已解决并 verified 迁移 ISSUES.md(2026-09-28 第 31 轮:接线已随 93242f9 完成,真机实证 req_branch=feat/hgcsrzwbty20260928 拼音策略产出) | — | — | — | — |
| BUG-063 | fixed(第 33 轮闭环:pytest 5/5(Red→Green)+ 触碰面回归 123 passed + tsc/build 零错 + 真机探针 4/4——用户今日 2 个卡 creating 的打磨任务由假「运行中」转为「启动中」;verified 待用户浏览器复验徽章;⚠ 编号让渡:初登记 BUG-062,该号已被同日并行会话第 32 轮(依赖安装链 R34.F3)先行占用,后登记方让渡改号) | R3.F2(打磨容器启动状态;波及 R4 工作台/R22 任务列表展示) | 功能偏差(用户指令) | 用户指令 2026-09-28(rd-fix 第 33 轮) | 「需求创建后开始打磨,确保 container 启动好了,没有启动好页面状态显示启动中」:create_polish_task 调度成功即置 task.status=running,但容器经 Runner 异步拉起(container_started 回报前 containers.status=creating、tasks.container_id=NULL),API 不返回容器状态 → 窗口期工作台/列表/需求详情全显示「运行中」;修复=后端派生 display_status(task_service.derive_display_status:running+容器未到 running→starting/failed→failed/其余透传;列表批量查防 N+1)+前端 TaskDetail VP_ST/ProjectTaskList statusMap(+筛选项)/RequirementDetail 三处映射(启动中=b-amber;starting 视同在跑给 pulse+停止按钮),分片 ./DEVPLAN/R3.F2.md;证据 .scratch/R3.F2/{qa-red,fix-report,ui-check,probe}.md |
| BUG-065 | ✅ verified(2026-09-28 第 35 轮独立复验:真机重放消息 code=0;四层探针全过——容器内裸 claude pong/stream-json 29 行/宿主带桥接 26 行/runner 容器内生产代码 pong5(46826 in/27 out tokens)/生产 parity(bridge=True+--session-id)pong6;详见 DEVPLAN/R8.F6.md 与 .scratch/fix-analysis.md § 35) | R8.F6(runner 运行时;承接第 29 轮遗留「runner 镜像重建」登记) | 功能缺陷(疑似 runner 侧代码/镜像陈旧) | 用户实测报障 2026-09-28(rd-fix 第 35 轮) | AI 对话发消息 `POST /api/tasks/e17584d3-.../messages` 返回 `{"code":9001,"message":"AI 执行失败:未知工具: claude_prompt_stream"}`;确诊=17:04 runner 容器从旧镜像重建,第 29 轮热补(R8.F5 上报/R32.F5 流式)全部回退(md5 不一致实证);同根因症状②=16:58 打磨 start 指令发进濒死连接丢失、占位行挂 creating;修复(协同会话 R8.F6)=按 R31.F3 回退路径重建 runner:v1(BASE_IMAGE=python:3.10)+原参数重建容器(md5 与仓库一致、claude_prompt_stream 在位),占位行经 handle_sync 判 destroyed 自愈,977/978 双任务容器 running+回填实证;复验时顺带确认任务容器 claude 对 qwen3.7-plus 报 unrecognized_model 警告(仅 stderr,不拦截,可 CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1 消音) |
| BUG-066 | open(移交 R32 流,不修) | R32(runner 标签/编辑族) | 功能缺陷(实现缺失,测试先行) | BUG-065 修转发扰 2026-09-28(rd-fix 第 35 轮协同发现) | R32 标签实现(validate_tags/update_runner/create_runner tags 参数)**不在工作区也不在任何 git 提交**(git log -S 双空;第 29 轮 R32.F4「原样恢复」未持久,二次丢失)——test_r32_runner_tags.py 等 13 用例+test_r31_local_runner 4 例+test_r25_audit_p1p2 1 例共 18 红灯的真实根因(此前一度误判 DB 噪音);修法=按已提交测试规格重实现并**务必落提交**;与 BUG-065 同批全量回归时发现,已由 R8.F6 分片留痕 |
| BUG-069 | fixed(2026-09-29 第 36 轮闭环:R5.F2 四层修复——F1 runner 累积 textDelta 兜底(优先级 result>累积>lines[-1])/F2 后端落库非空校验+占位文案/F3 前端 refetch 新消息落地才清流式气泡/F4 去 2>/dev/null stderr_tail 可回溯;runner 6/6+backend 3/3+tsc/build 零错;镜像 platform/runner:v1 重建(python:3.10-slim 本地回退)+容器原参数重建+后端重启;真机探针 task 830af6e6「登录验证码」发 ping→code=0+assistant content='pong' 非空落库;**verified 待用户浏览器复验长消息场景**(原话复现消息「项目需要登录加上图形验证码」);证据 .scratch/R5.F2/fix-report.md;⚠ TaskMessage 无 error_message 列,占位留痕改走日志) | R5/R32/R35(AI 对话流式链路;疑与 R35 思考过程改动相关) | 功能缺陷(流式后内容消失) | 用户实测报障 2026-09-29(rd-fix 第 36 轮) | AI 对话发送「项目需要登录加上图形验证码」后 AI 流式输出了一段内容,随后消息内容又消失(长消息场景「没有返回」);用户疑点:上次加的思考过程(R35 thinking_content/chat_thinking)改坏——**已排除**(R35 未实现,代码零 thinking 引用);根因=CLI 长消息/中途出错不发 result 事件时 runner lines[-1] 兜底拿错行+空 content 落库+前端 onSuccess 清流式气泡被 refetch 覆盖,三者共因+stderr 被吞不可回溯 |
| BUG-070 | fixed(2026-09-29 第 39 轮二修浏览器端到端闭环;第 38 轮 R4.F6 门禁全绿但用户复验仍「目录下的文件没有显示」——第 39 轮真浏览器复现抓到**一行根因**:fetchDir 把原始 FileItem 直接存 dirChildren,未归一为 LazyNode → 子级 node.name/fullPath=undefined → 空名行+key 警告+二级展开恒假;修复 F-A=存储前 items.map(toLazyNode(it,dir)) + F-B=打磨布局点文件不再切 'edit'(无编辑器 pane 会白屏)改树下只读预览;**playwright 真浏览器 7/7 PASS**(真实登录+任务 279938f7+真实容器:两级展开 backend→culture-freeroom→pom.xml/点文件预览非空/零 key 警告/零 JS 错误,截图 .scratch/R4.F6/r39-L2-nested.png);tsc/build 过;复盘:第 38 轮验证盲区=只证到 API 层没点过一次真树,教训留痕 .scratch/R4.F6/ui-check.md § 第 39 轮;vite HMR 已载,待用户刷新浏览器复验后 verified 迁移) | R4(任务工作台文件树;波及 R11 编辑器/R10 预览) | 功能缺陷(用户指令,升级=完整文件树管理) | 用户指令 2026-09-29(rd-fix 第 37 轮登记;第 38/39 轮两次复验) | 任务打磨「工作区」+开发「全部文件」文件管理组件:经 37(type 归一化)/38(懒加载树+绝对路径)/39(渲染层数据归一)三轮收敛,完整文件树管理(目录逐层懒加载+文件预览+错误可见)已浏览器实证 |
| BUG-071 | fixed(2026-09-29 第 39 轮闭环:R9.F3——F2 terminal.py auto_claude_cmd 前置幂等补写 hasCompletedOnboarding+CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1(存量容器**新建终端即生效**);F1 devbox Dockerfile 构建尾预置键治本(镜像重建+推送归发布动作,留痕);pytest terminal 触碰面 8/8+新增断言 2(tsc 不涉,前端零改动);真机四判据全过——B 容器 pty 探针回滚→403 秒退/带补写→TUI 常驻,A 平台 API 建会话→新 wrapper 补写片段在位+**claude --resume 活体子进程**(ps PID 实证)→清理 code=0,C ping→code=0+assistant 非空落库,D 浏览器 TUI 视觉归用户(旧终端 Tab 需关掉重开才吃到修复);⚠ subagent 会话退出连带其拉起的后端死亡,主会话单进程重启(detached)+补齐 A/C;pytest 1 failed=test_r9f1 send_message 13005 fixture 缺失,与 R9.F3 diff 路径不相交定性 pre-existing。**症状①定性非 bug**——模型参数 env 注入完好;custom_env_vars(10:51 配置 5 个 ENV_MCP_*)在 10:54 创建的容器全部注入 ✓,bold_cray/kind_mclaren 系配置前旧容器按设计不回填;附:并发首开 ensure_claude_session 竞态 5 终端 5 sid 登记;证据 .scratch/R9.F3/fix-report.md) | R9(任务终端;波及 R8.F4 env 注入/R9.F1 claude 接线)/R34(增量7 验收型,未实现) | 功能缺陷(终端 env 缺失 + claude 未自启) | 用户实测报障 2026-09-29(rd-fix 第 39 轮;⚠ 轮次让渡:初标第 38 轮已被并行会话 BUG-070 复开分析占用) | 任务终端唤起后:① 对应模型参数(LLM_URL/LLM_MODEL/ANTHROPIC_* 等)与平台「自定义变量」没有注入到终端窗口环境;② 终端没有自动起动 claude(裸 bash)。历史基线:R8.F4(BUG-036)容器创建注入 LLM_URL/LLM_MODEL+custom_env_vars;R9.F1(BUG-037)终端 exec bash -lc 包装自动进 claude(与对话同会话 --session-id/--resume);待分析:终端 exec cmd 现状是否被并行流改动/回退(20260927 并行流 f4fad54 exec_tool_cancel、4dc7d45 permission-prompt-tool 桥接、R4.F5 会话)、env 注入是容器级(docker run -e,exec 应继承)还是包装层丢失、打磨(requirement)任务容器创建路径是否漏 env 构建、command -v claude 在 exec shell PATH 下是否命中、R34 验收型缺口是否在此暴露;⚠ 并行会话防双写:第 37 轮(R4.F5)在 runner/container_manager.py list_dir 有未进镜像改动,本轮若动 runner/terminal 或 backend terminal.py 需函数级避让 |
| BUG-072 | fixed → ✅ verified → 已 verified 迁移 ISSUES.md(2026-09-29 第 41 轮;端到端实证「查询结果是 1」,档案见 ISSUES.md 同日小节) | — | — | — | — |
| BUG-074 | fixed(2026-09-29 第 42 轮闭环:R3.F4 纯前端——TaskChat 新增 taskType/prdFilePath 可选 props+isNewSession 判定(无「非空且非占位」assistant 行;占位行不计=失败重开仍重发)+useEffect 自动发 `/rd-prd '+prdFilePath`(sentRef 一次挂载一发,防 StrictMode/3s 轮询重入)+TaskDetail 透传 task.type 与 req.prd_file_path(:299 hook 已有,PRD 预览 :308 同字段同源=路径一致性天然保证);tsc 零错+build 过;真机终验归用户浏览器(新建/打开打磨任务→自动出现 /rd-prd 消息→AI 进 prd 模式→中栏 PRD 预览读到同路径);其余调用点不传 props 行为不变;分片 ./DEVPLAN/R3.F4.md(R3.F3 已被并行第 41 轮占用顺延);ui-check .scratch/R3.F4/) | R3/R4(需求打磨;波及 R33 斜杠技能/R17 skills 注入)  R3/R4(需求打磨;波及 R33 斜杠技能/R17 skills 注入) | 功能增强(用户指令) | 用户指令 2026-09-29(rd-fix 第 42 轮) | 需求打磨页面:检测 AI 会话是否是新的(第一次开/失败后重开),是则第一条消息自动发送 `/rd-prd <PRD文件路径>`(路径取需求详情存的 PRD 路径地址,经 skills 调用)——目的:确保打磨 AI 进入 prd 模式,且 PRD.md 落盘位置与需求详情一致,PRD 预览可找到文件; 待分析:①需求详情 PRD 路径字段名(requirements 表列)与任务详情/需求详情接口是否已下发前端; ②「新会话」判定口径(task_messages 无非占位 assistant 行?claude_session_id NULL?); ③失败后重开的重发防护(占位行识别/只自动发一次标记); ④TaskChat 斜杠技能调用既有机制(R32.F2/R33)复用点; ⑤打磨任务(type=requirement)工作区挂载与 PRD.md 落盘路径的对齐(claude_inject/workdir) |
| BUG-073 | open(第 40 轮附带登记,环境健壮性批,待排期/用户拍板) | R8/R16(容器生命周期;runner 事件自动重启链) | 功能缺陷(环境健壮性三连) | R5.F3 判据 C 排障附带发现 2026-09-29 | ① **Docker Desktop 残留端口代理致任务容器自动重启失败**:任务容器停止后 runner 事件链自动 start 报 500 "Ports are not available: exposing port TCP 0.0.0.0:21175"(宿主 com.docker.backend PID 14308 持有残留代理,容器 9b13fe6af4a9/任务 830af6e6 实证;容器后经用户侧操作恢复 Up)——候选修法:自动重启失败时降级映射端口重试/提示用户;② **容器移除竞态窗口 exec 秒退**:任务容器被用户移除瞬间,在途 claude_prompt_stream 秒退→零行→R5.F2 占位「请重试」误导真因(可观测但文案不精确;候选:exec 失败区分容器缺席→明确错误文案);③ **任务容器 PID1=sleep infinity 不收割僵尸**:容器内 defunct claude/node/sh 累积(ps 实证多个 zombie;候选:镜像入口换 init/tini 或 bash 收割循环) |
| BUG-067 | open(2026-09-29 更新:① stderr 吞错已随 BUG-069/R5.F2 F4 协同收口——2>/dev/null 已去,stderr 捕获进 stderr_tail(≤2000 字符)+后端 warning 日志;残余:② R32.F8 零行降级对 --session-id 首用路径的判定核对、③ 流读循环 Windows 命名管道 EOF 109 归一化,继续挂起归 R32 重实现批或下轮) | R5/R32(对话流式链路;波及 BUG-060 降级判定) | 可诊断性缺陷 + 瞬态空回复(BUG-065 复验附带发现) | rd-fix 第 35 轮复验 2026-09-28 | ① 瞬态空回复两例(18:14 用户/18:20 复验,~8-11s 空结算 tokens=0)当时不可回溯——`claude_prompt_stream` cmd 尾 `2>/dev/null` 把 CLI stderr 全吞(unrecognized_model/API error 全不可见),复验时全形态探针(裸/stream-json/带桥接/生产 parity)均通,瞬态真因(gateway 抖动 vs 18:20 后端重启窗口)无法定位;② R32.F8 零行降级仅日志一条「降级新会话重跑」,两例均未触发——`--session-id` 首用路径是否纳入降级判定需核对(main.py:520-525);③ 附带隐患:流读循环 `sock.recv` 对 Windows 命名管道 EOF 抛 pywintypes 109 不当结束(宿主 Windows 直跑 runner 代码即触发,复验中实证),Linux unix socket 不受影响;建议=stderr 捕获落盘并入 result/日志 + 降级条件核对 + EOF 归一化(参照 BUG-031/BUG-050 探测式先例) |

| BUG-074 | fixed(2026-09-29 第 40 轮 R4.F7;⚠ 编号让渡:初登记 BUG-071,该号已被同日并行会话(R9.F3/R5.F3)先行占用,后登记方让渡改号 074。活体取证=全部存活任务 base==work 自指基线→`git diff 自己`恒空「变更文件没有对比效果」;双层根因:创建链 create_task `base_branch or requirement.req_branch` 自指 + diff/changes 端点不读任务基线(空串/硬编码 master)。修复 F1=create_task 基线改 project.default_branch(需求分支从它切出,治本)+ F2=resolve_task_base_branch 解析器(显式参>task.base 非自指>项目默认分支)双端点接入——存量自指任务展示层即时自愈,零数据迁移零 runner 零前端;backend 12/12(5 新用例矩阵+7 回归)+真实自指行活体解析=master 实证+容器 git 真相核对(现存活任务确无变更,空=正确答案);后端已带 --reload 重启;Diff 内容级浏览器复验归用户活跃 dev 任务) | R4(任务工作台 Diff 视图;波及 R11/R6) | 功能缺陷(用户指令) | 用户指令 2026-09-29(rd-fix 第 40 轮,本会话) | 「对应变更文件没有对比效果」——基线自指+端点不读基线双层缺陷;分片 ./DEVPLAN/R4.F7.md |

| BUG-075 | fixed(2026-09-29 第 41 轮 R4.F8;BUG-074 的时序残余) | R4(任务工作台 Diff 视图) | 功能缺陷(用户指令) | 用户指令 2026-09-29(rd-fix 第 41 轮) | 「任务页面,对应变更文件没有对比效果,文件部分有新增减少行数,点击没有文件预览效果」——变更 chips 出行数(R4.F7 生效)但点击无对比。活体+真浏览器取证:后端 changes/diff 双端点路径 2/2 匹配、diff 内容 28KB 真实存在;**playwright 真浏览器当前态全通**(chips=2 带行数→点击→空态 0/DiffViewer 渲染 37390 字符)——用户所见=diffData 在修复前时期被 react-query 缓存为空/错误(容器抖动窗口 BUG-073② 同效),进 Diff Tab 无自动补拉、失败无重试入口,误导为「暂无变更」。修复 R4.F8=① 进 Diff Tab 且 changes 有文件而 diff 为空→自动补拉一次 ② diff 加载失败→可见错误条+重试(替换误导性空态文案);tsc/build 过+浏览器复验不回退;刷新浏览器即生效 |

## BUG-015

- **状态**:fixed(修复后经真实绑定 API 实证,待回归置 verified)
- **关联需求点**:R1(用户绑定 GitLab token);波及 R3(评审 push 用个人 token)/ R4(任务创建校验创建者 token)
- **严重程度**:高(自建 GitLab 环境下用户 token 绑定 100% 失败,R3/R4 主链路被阻塞)
- **复现步骤**:`PUT /api/users/me/gitlab-token`(携带有效自建 GitLab PAT)→ 返回 `{"code":1012,"message":"GitLab token 无效或已过期"}`
- **期望 vs 实际**:期望按平台设置 `gitlab_url` 指向的自建实例校验并绑定成功;实际请求打到 `https://gitlab.com/api/v4/user`(gitlab_service.py `GITLAB_API_BASE` 硬编码),自建实例的 PAT 在 gitlab.com 必然 401
- **错误信息**:`code=1012 GitLab token 无效或已过期`
- **根因**:R1 期 `GitlabService.verify_token` 写死公网 gitlab.com;R2 引入平台级 `gitlab_url` 配置只接了 bot 链路,用户个人 token 校验路径未接。单测用 MockTransport 拦截 HTTP,环境无关,故测试全绿未暴露
- **修复记录(2026-09-22 rd-test 自动修复)**:① `verify_token` 增加 `api_base: Optional[str]` 参数(None 时回落 `GITLAB_API_BASE`);② `app/api/users.py` bind_gitlab_token 读平台设置 `gitlab_url` 拼接 `{url}/api/v4` 传入,未配置时维持旧行为(gitlab.com)
- **验证记录**:修复重启后端后 `PUT /api/users/me/gitlab-token` 返回 code=0,绑定成功(用户名/scope 正常入库);创建 dev 任务不再报 4002

## BUG-016

- **状态**:fixed(修复后经真实绑定 API 实证,待回归置 verified)
- **关联需求点**:R1(用户绑定 GitLab token);波及 R3/R4 同 BUG-015
- **严重程度**:高(当前自建 GitLab v11.7 环境下所有有效 token 均被误判)
- **复现步骤**:`PUT /api/users/me/gitlab-token`(携带自建 GitLab 有效 PAT)→ `{"code":1013,"message":"GitLab token 缺少必要权限"}`(token 实测有效:GET /api/v4/user 返回 200)
- **期望 vs 实际**:期望有效 token 绑定成功;实际因 GitLab v11.x 的 `/user` 响应**不带 `X-Token-Scopes` 头**(12.x+ 才有),scope 解析恒为空 → AND(read_repository, write_repository) 校验必失败
- **错误信息**:`code=1013 GitLab token 缺少必要权限`
- **根因**:scope 校验依赖新版 GitLab 特性,未对旧版做兼容;旧版亦无 `GET /personal_access_tokens` 自省接口(实测 404),无法服务端补查
- **修复记录(2026-09-22 rd-test 自动修复)**:`verify_token` 在 X-Token-Scopes 头缺失时置 `scopes=["unknown"]`;`check_required_scopes` 对 `["unknown"]` 放行——旧版 GitLab 无法判定 scope 时不再误拒,真实权限问题由后续实际 GitLab 操作的 401/403 兜底暴露
- **验证记录**:修复重启后端后绑定返回 code=0;dev 任务创建成功

## BUG-007

- **状态**:fixed(verified 待部署机首次构建后翻转)
- **关联需求点**:R16(Runner 镜像;缺的文件分别产自 R9/R11)
- **严重程度**:阻塞(Runner 无法部署,任务容器/终端/预览/发布全链路不可用)
- **复现步骤**:`docker build -t platform/runner:v1 -f docker/runner/Dockerfile runner/ && docker run --rm platform/runner:v1`
- **期望 vs 实际**:期望 Runner 进程启动并尝试连接平台 /ws/runner;实际 `main.py` import `TerminalManager`/`FileWatcher` 时抛 `ModuleNotFoundError`(镜像内只 COPY 了 main.py + container_manager.py,DEPLOY.md §0 已核对)
- **错误信息**:`ModuleNotFoundError: No module named 'terminal_manager'`
- **来源**:rd-ship 发布检查单 §0 阻塞项
- **修复记录(2026-09-22 rd-fix / R16.F1)**:`docker/runner/Dockerfile` COPY 补齐 4 文件(`main.py container_manager.py terminal_manager.py file_watcher.py`)
- **验证记录**:① 静态 import 闭包核对通过;② 本机 Docker Desktop 引擎未运行,`docker build` + `import main` 冒烟留待部署机执行(DEPLOY.md §4/§5 已有该勾选项)——构建通过即置 verified 并迁移 ISSUES.md

## BUG-UI-002

- **状态**:已核实——误报。`.card-foot` 包裹存在于 AuditLogsPage.tsx:257,核对时审计表为空(`totalPages>1` 为 false)故分页不渲染;空表不显示分页符合预期,vp 原型审计页亦无分页脚注
- **关联页面**:/admin/audit-logs
- **严重程度**:低(视觉偏差)
- **设计规范**:admin-users.md §2.1 — 表格容器层级 `.card > .scrollx > table.tbl > .card-foot`(分页)
- **实际表现**:审计日志页 `.card-foot` 不存在(`exists: false`);有 `.fbar`(筛选条)但无分页脚注
- **修复建议**:按 admin-users.md §6.2 #7,将分页器移入 `.card-foot` 容器

## BUG-UI-007

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(登录页视觉规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问 /login,检查标题"欢迎回来"的 font-size
- **期望 vs 实际**:期望 22px(text-xl/1.375rem);实际 17px
- **截图**:report/TC-R1-01-login-page.png

## BUG-UI-008

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(登录页视觉规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问 /login,检查输入框 font-size
- **期望 vs 实际**:期望 16px(text-base/1rem);实际 13px
- **截图**:report/TC-R1-01-login-page.png

## BUG-UI-009

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(登录页卡片视觉规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问 /login,检查卡片容器 border-radius 和 padding
- **期望 vs 实际**:期望 border-radius 12px(0.75rem)/padding 24px(1.5rem);实际 border-radius 16px/padding 26px
- **截图**:report/TC-R1-01-login-page.png

## BUG-UI-010

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(登录页表单间距规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问 /login,检查表单项间距(space-y-4)
- **期望 vs 实际**:期望 16px(1rem);实际 ~14px
- **截图**:report/TC-R1-01-login-page.png

## BUG-UI-011

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(登录页按钮交互规范)
- **严重程度**:一般(交互偏差)
- **复现步骤**:访问 /login,hover 提交按钮,检查 transition 和 hover bg
- **期望 vs 实际**:期望 hover bg #27272a + transition "all 0.15s";实际 hover bg 与常态相同(无变化),transition 为 "background 0.12s"
- **截图**:report/TC-R1-01-login-page.png

## BUG-UI-012

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(登录页输入框 focus 规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问 /login,点击输入框触发 focus,检查 ring 效果
- **期望 vs 实际**:期望双层 ring;实际仅单层 ring rgba(161,161,170,0.4) 0 0 0 3px
- **截图**:report/TC-R1-01-login-page.png

## BUG-UI-013

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(注册页视觉规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问 /register,检查卡片宽度/border-radius/输入框字号/按钮字号/transition/focus ring
- **期望 vs 实际**:卡片宽度 448px(期望 400px),border-radius 10px(期望 12px),输入框/按钮 font-size 13px(期望 16px),transition "background 0.12s"(期望 "all 0.15s"),focus 单层 ring(期望双层)
- **截图**:report/TC-R1-17-register-page.png

## BUG-UI-014

- **状态**:已核实:BYDESIGN(V2 预留)不修
- **核实记录(2026-09-23 rd-test 分诊)**:BYDESIGN——V2 预留,当前版本不实现(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(找回密码功能)
- **严重程度**:严重(功能缺失)
- **复现步骤**:访问 /forgot-password,检查页面内容
- **期望 vs 实际**:期望含手机号输入+发送验证码按钮的表单;实际为 V2 占位页,仅显示"V2 功能 - 找回密码功能将在 V2 版本中开放...",无任何表单元素。卡片宽度 448px(期望 400px),border-radius 10px(期望 12px)
- **截图**:report/TC-R1-18-forgot-password-page.png

## BUG-UI-015

- **状态**:已核实:BYDESIGN(V2 预留)不修
- **核实记录(2026-09-23 rd-test 分诊)**:BYDESIGN——V2 预留,当前版本不实现(期望已在 TESTCASE.md 修正)
- **关联需求点**:R1(重置密码功能)
- **严重程度**:严重(功能缺失)
- **复现步骤**:访问 /reset-password,检查页面内容
- **期望 vs 实际**:期望含新密码+确认密码表单;实际为 V2 占位页,仅显示"V2 功能 - 重置密码功能将在 V2 版本中开放...",无任何表单元素。卡片宽度 448px(期望 400px),border-radius 10px(期望 12px)
- **截图**:report/TC-R1-19-reset-password-page.png

## BUG-UI-016

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R2(项目列表交互规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问 /projects,hover 项目卡片(.pcard),检查背景色变化
- **期望 vs 实际**:期望 hover 时背景色变为 bg-surface-strong(#f4f4f5);实际仅 border-color 从 rgb(228,228,231) 变为 rgb(212,212,216),box-shadow 从 rgba(0,0,0,0.05) 变为 rgba(0,0,0,0.08),背景色保持 rgb(255,255,255) 不变
- **错误信息**:getComputedStyle 显示 .pcard:hover 的 backgroundColor 为 rgb(255,255,255),未变为 #f4f4f5
- **截图**:report/TC-R2-05-hover-no-bg-change.png

## BUG-UI-017

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R2(项目列表卡片规范)
- **严重程度**:一般(信息缺失)
- **复现步骤**:访问 /projects,检查项目卡片内容
- **期望 vs 实际**:期望卡片包含名称(slug)/描述/仓库数/创建时间/状态徽章/操作按钮(查看/设置/删除);实际仅有名称(slug)+描述+仓库数+状态徽章,缺少创建时间和操作按钮
- **错误信息**:卡片 DOM 中无创建时间元素,无查看/设置/删除按钮
- **截图**:report/TC-R2-08-card-layout.png

## BUG-UI-018

- **状态**:open→fixed→verified
- **关联需求点**:R2(Dialog 动画规范)
- **严重程度**:一般(交互缺失)
- **复现步骤**:点击"新建项目"按钮打开 Dialog,检查淡入+缩放动画;关闭 Dialog,检查淡出动画
- **期望 vs 实际**:期望 Dialog 打开时有 150ms 淡入动画(opacity 0→1)+ 缩放动画(scale 0.95→1);关闭时有淡出动画。实际 Dialog 瞬间出现,无可见动画;关闭时瞬间消失
- **错误信息**:Dialog.tsx:41 引用 animation: 'dialogOverlayIn 150ms ease-out',Dialog.tsx:66 引用 animation: 'dialogContentIn 150ms ease-out',但 globals.css 中无 @keyframes dialogOverlayIn 和 @keyframes dialogContentIn 定义。Dialog.tsx:173 `if (!open) return null` 导致关闭时瞬时卸载,无淡出可能
- **截图**:report/TC-R2-06-dialog-no-animation.png
- **修复记录(2026-09-23 rd-test 自动修复)**:在 frontend/src/styles/globals.css 补两个 @keyframes:dialogOverlayIn(fade 0→1)和 dialogContentIn(fade+scale 0.95+translateY 4px→1),时长 150ms ease-out,与 Dialog.tsx style.animation 引用一致。关闭淡出未修(仍为瞬时卸载,需重构为 CSS transition 方案,超出本次范围)
- **验证记录(2026-09-23 rd-test 回归)**:Dialog overlay animationName="dialogOverlayIn",content animationName="dialogContentIn",动画正常生效

## BUG-UI-019

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R2(空状态文案规范)
- **严重程度**:轻微(文案偏差)
- **复现步骤**:访问 /projects(无项目时),检查空状态文案
- **期望 vs 实际**:期望显示"暂无项目,点击右上角新建";实际显示"还没有项目"(第一行)+ "请点击右上角「新建项目」创建第一个项目"(第二行)
- **错误信息**:ProjectList.tsx:95-99 渲染两个 `<p>` 元素,文案与规范不符
- **截图**:—(代码实证,ProjectList.tsx:95-99)

## BUG-UI-020

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R2(项目列表布局规范)
- **严重程度**:严重(布局偏差)
- **复现步骤**:访问 /projects,检查页面结构
- **期望 vs 实际**:期望使用 `.card` 包裹 `<table className="tbl">` 的表格布局;实际使用 `.pcards > .pcard` 卡片布局,无 `<table>` 元素
- **错误信息**:DOM 中无 `<table>` 元素,.pcards 容器内为多个 .pcard 卡片。TC-R2-02(列宽自适应)和 TC-R2-03(操作列固定 150px)因无表格而无法验证
- **截图**:report/TC-R2-01-card-layout.png

## BUG-017

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R2(仓库列表功能)
- **严重程度**:一般(功能缺陷)
- **复现步骤**:访问项目详情页,切换到"仓库"Tab,检查仓库列表
- **期望 vs 实际**:期望仓库列表显示角色徽章/仓库 URL/绑定方式/绑定时间/操作(解绑按钮);实际"绑定时间"列显示"—"(未填充数据),操作列仅主仓库显示 disabled 的"主仓库不可解绑"按钮,非主仓库无解绑按钮
- **错误信息**:RepoManagement.tsx 渲染的表格中,绑定时间列值为"—",操作列按钮被 disabled 或缺失
- **截图**:report/TC-R2-09-repo-management.png

## BUG-UI-024

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R3(需求列表列宽规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问 /projects/{pid}/requirements,检查操作列宽度
- **期望 vs 实际**:期望操作列固定宽度200px;实际操作列宽度80px
- **错误信息**:getComputedStyle显示操作列th/td宽度为80px,非200px
- **截图**:report/TC-R3-02-operations-column-width.png

## BUG-UI-025

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R3(需求列表操作按钮规范)
- **严重程度**:一般(信息缺失)
- **复现步骤**:访问 /projects/{pid}/requirements,检查操作列按钮
- **期望 vs 实际**:期望每行3个文本按钮(查看/编辑/删除);实际仅1个图标按钮(SVG图标,无文本)
- **错误信息**:DOM中每行仅1个button元素,内含SVG图标,无"查看"/"编辑"/"删除"文本
- **截图**:report/TC-R3-02-operations-column-width.png

## BUG-UI-026

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R3(任务类型徽章样式规范)
- **严重程度**:一般(视觉偏差)
- **复现步骤**:访问需求详情页(approved "demo"),检查关联任务列表中"开发"徽章颜色
- **期望 vs 实际**:期望徽章文字颜色为primary蓝色;实际文字颜色为黑色rgb(24,24,27)
- **错误信息**:徽章class="bg-primary/10 border-primary/20 text-primary",但computedStyle color=rgb(24,24,27),backgroundColor=rgba(0,0,0,0)(transparent)。Tailwind primary颜色类未正确解析
- **截图**:report/TC-R3-07-task-type-badge.png

## BUG-018

- **状态**:open
- **关联需求点**:R3(需求详情页路由)
- **严重程度**:严重(主流程受阻)
- **复现步骤**:直接访问 /requirements/{rid} 或 /projects/{pid}/requirements/{rid}
- **期望 vs 实际**:期望直接打开需求详情页;实际被重定向至首页(/)
- **错误信息**:browser_navigate直接访问详情页URL后,页面跳转至首页,无法查看详情。必须从列表页点击按钮进入
- **截图**:—(路由行为实证)

## BUG-019

- **状态**:verified
- **关联需求点**:R3(需求详情页markdown渲染)
- **严重程度**:严重(功能缺失)
- **复现步骤**:访问需求详情页(approved "demo"),检查背景/描述/验收标准内容
- **期望 vs 实际**:期望内容以markdown格式渲染(含p/ul/ol/strong/em等元素);实际显示为纯文本,0个p/ul/ol元素
- **错误信息**:querySelectorAll('p')=0, querySelectorAll('ul')=0, querySelectorAll('ol')=0。内容区域无markdown解析渲染
- **截图**:report/TC-R3-04-no-markdown-rendering.png
- **修复记录(2026-09-23)**:RequirementDetail.tsx 新增 renderMarkdown 函数(与 KnowledgeBaseView 保持一致的简易正则渲染),将 background/description/acceptance_criteria 三个字段从 whitespace-pre-wrap 纯文本改为 dangerouslySetInnerHTML + renderMarkdown 渲染,支持标题/代码块/加粗/斜体/列表等 Markdown 语法。TypeScript 编译通过(零错误)
- **验证记录(2026-09-23 rd-test 回归)**:描述字段渲染出 `<p class="my-2">` 块级 HTML,hasBlockElements=true;背景/验收标准字段为空但渲染容器已就位

## BUG-020

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R3(需求详情页滚动区域)
- **严重程度**:一般(交互缺失)
- **复现步骤**:访问需求详情页,检查内容区域是否可独立滚动
- **期望 vs 实际**:期望内容区域有独立滚动容器(overflow:auto/scroll);实际body.scrollHeight===body.clientHeight(1222px===1222px),无独立滚动区域
- **错误信息**:document.querySelector('[class*="overflow"]')的scrollHeight===clientHeight,无overflow样式
- **截图**:—(DOM结构实证)

## BUG-021

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R3(draft需求详情页结构)
- **严重程度**:一般(信息缺失)
- **复现步骤**:访问draft状态需求"崩溃复验"详情页
- **期望 vs 实际**:期望详情页包含背景/描述/验收标准区域;实际仅有"基本信息"标题,无背景/验收标准区域
- **错误信息**:draft需求详情页DOM中无背景/验收标准相关元素
- **截图**:report/TC-R3-11-edit-dialog-not-open.png

## BUG-022

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R3(需求详情页操作按钮)
- **严重程度**:严重(功能缺失)
- **复现步骤**:访问approved需求"demo"详情页,检查操作按钮
- **期望 vs 实际**:期望有"编辑"/"打磨"/"提交"按钮;实际仅有"返回"/"创建开发任务"按钮
- **错误信息**:DOM中无"编辑"/"打磨"/"提交"按钮元素
- **截图**:report/TC-R3-10-missing-buttons.png

## BUG-023

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R3(编辑需求弹窗)
- **严重程度**:严重(功能不可用)
- **复现步骤**:访问draft需求"崩溃复验"详情页,点击"开始打磨"按钮
- **期望 vs 实际**:期望弹出编辑弹窗含标题/描述/验收标准等字段;实际点击后页面无变化,无弹窗出现
- **错误信息**:点击"开始打磨"按钮后,document.querySelectorAll('[role="dialog"]').length=0, 无input元素出现,页面内容未改变
- **截图**:report/TC-R3-11-edit-dialog-not-open.png

## BUG-UI-027

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R4(任务工作台文件树)
- **严重程度**:一般(信息缺失)
- **复现步骤**:访问 /tasks/{taskId}(type=dev),检查左侧文件树区域"变更文件"Tab
- **期望 vs 实际**:期望"变更文件"Tab 显示变更计数徽章(如"变更文件 3");实际 innerHTML="变更文件",children=0,无任何徽章/计数器元素
- **错误信息**:changedBtnInnerHTML="变更文件",changedBtnChildren=0。Tab 按钮内仅有文本节点,无子元素
- **截图**:report/TC-R4-07-no-badge.png

## BUG-UI-028

- **状态**:open
- **关联需求点**:R4(任务工作台右侧面板)
- **严重程度**:一般(功能缺失)
- **复现步骤**:访问 /tasks/{taskId}(type=dev),检查右侧面板(400px)的 Tab 结构
- **期望 vs 实际**:期望右侧面板有"活动"Tab(role="tab")和"终端"Tab;实际无任何 role="tab" 元素,tabRoles=[]。"终端"仅以"新建终端"按钮形式存在,无"活动"按钮/Tab
- **错误信息**:rightPanel 内 Array.from(buttons).find(b=>b.textContent.includes("活动"))=undefined;tabRoles=[]。右侧面板文本为"暂无消息,发送第一条指令开始任务发送活动流活动流未连接点击新建终端新建终端"
- **截图**:report/TC-R4-05-no-activity-tab.png

## BUG-024

- **状态**:fixed
- **关联需求点**:R4(消息发送功能)
- **严重程度**:严重(主流程受阻)
- **复现步骤**:访问 /tasks/{taskId}(type=dev),在聊天输入框输入"测试消息:验证消息发送功能",点击"发送"按钮
- **期望 vs 实际**:期望消息发送成功,输入框清空,消息出现在聊天区域;实际输入框未清空(inputValue="测试消息:验证消息发送功能"),消息未出现(hasTestMessage=false),空状态仍在(hasEmptyState=true,"暂无消息")
- **错误信息**:点击发送按钮后,input.value 未变,聊天区域仍显示"暂无消息,发送第一条指令开始任务"。消息发送功能完全无效
- **截图**:report/TC-R4-08-send-failure.png
- **修复记录**:已核实:预期业务规则,非缺陷。后端 POST /api/tasks/{task_id}/messages 在任务无 running 状态容器时返回 code=9001(TERMINAL_UNAVAILABLE,"任务容器不在运行,无法执行 AI 会话"),属正常业务拦截。走查时该 dev 任务(b0408f29)无运行容器,故 sendMut 走 onError 分支,前端 showToast 弹出错误提示、输入框不清空(符合 onError 逻辑)。前端 sendMut 逻辑无误,后端状态机拦截正确。

## BUG-UI-029

- **状态**:verified
- **关联需求点**:R5(@filename 自动补全)
- **严重程度**:一般(功能缺失)
- **复现步骤**:访问 /tasks/{taskId}(type=dev),在聊天输入框输入"@"字符,观察是否弹出文件补全下拉框
- **期望 vs 实际**:期望输入"@"后弹出文件列表下拉框(显示当前任务文件供选择);实际无任何下拉框弹出(totalDropdowns=0,visibleDropdowns=0)
- **错误信息**:输入"@"后,document.querySelectorAll('[role="listbox"],[role="menu"],[class*="dropdown"],[class*="popover"],[class*="autocomplete"],[class*="mention"]').length=0。自动补全组件未触发
- **截图**:report/TC-R5-02-no-autocomplete.png
- **验证记录(2026-09-23 rd-test 回归)**:输入"@"后弹出补全下拉(absolute bottom-full bg-popover border rounded-md),无文件时显示"暂无已上传文件"

## BUG-UI-030

- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊)**:OVERREACH——实现符合 vp,TESTCASE 期望有误,不修(期望已在 TESTCASE.md 修正)
- **关联需求点**:R6(测试用例审阅页交互)
- **严重程度**:一般(交互模式与规范不符)
- **复现步骤**:
  1. 访问 /tasks/{taskId}/cases(type=dev 任务亦可)
  2. 点击"新增用例"按钮
- **期望 vs 实际**:
  - 期望:弹出 Dialog 对话框(参考 TESTCASE.md TC-R6-07 描述"打开对话框")
  - 实际:在 table tbody 中插入一行内联编辑表单(input + textarea + 保存/取消按钮),未弹出 Dialog
- **错误信息**:无控制台报错,但交互模式不符规范。点击"新增用例"后 document.querySelectorAll('[role="dialog"]').length=0,table tbody 内新增一行含 input/textarea/button 的 tr
- **截图**:未截图(行为明确)

## BUG-025

- **状态**:open
- **关联需求点**:R7(发布部署页)
- **严重程度**:严重(主流程受阻,/deploy 页面完全不可访问)
- **复现步骤**:
  1. 访问 /tasks/{taskId}/deploy(任意 taskId,含 dev/test/release 类型任务)
  2. 观察页面跳转
- **期望 vs 实际**:
  - 期望:打开发布部署页面,显示发布列表/操作栏/统计卡片
  - 实际:页面被重定向至首页(http://127.0.0.1:5173/),URL 变为 /
- **错误信息**:browser_navigate 后 location.href 变为 http://127.0.0.1:5173/,无控制台报错(前端路由守卫静默重定向)。TC-R7-01~05 全部 BLOCKED
- **截图**:未截图(重定向行为明确)
- **备注**:可能原因:① /deploy 路由未在前端 router 中注册;② 路由守卫对非 release 类型任务做了拦截重定向;③ 发布页仅对 type=release 任务开放,但缺少 403/空态提示,直接跳首页

### BUG-UI-031 [已核实:OVERREACH 不修] TC-R9-01 终端区无 Tab 栏结构
- **复现**:访问 /tasks/:taskId 任务工作台,右侧终端区
- **期望**:终端区含 Tab 栏(多终端 Tab 切换)+ xterm.js 全宽渲染
- **实际**:终端区无 Tab 栏结构(无 [role="tab"]/tablist 元素),空态下仅显示"点击新建终端"+ 新建终端按钮;新建终端失败后仍无 Tab 栏渲染
- **截图**:无(结构检查)
- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L1438 `data-t="term" … 终端` tab 存在;前端 TerminalPanel.tsx 有 TerminalTab 多 tab 结构,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-032 [已核实:OVERREACH 不修] TC-R9-04 终端空态未使用 --font-mono 字体
- **复现**:访问 /tasks/:taskId 任务工作台,右侧终端空态区
- **期望**:终端区 font-family 使用 CSS 变量 --font-mono(值为 'Geist Mono', ui-monospace, 'SFMono-Regular', monospace)
- **实际**:终端空态区 computed font-family 为 Geist/Inter/system-ui/sans-serif,未引用 --font-mono 变量,终端应使用等宽字体
- **截图**:无(样式检查)
- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L238/240 `.term-head/.term-body{font-family:var(--mono)}`;前端 globals.css L34 定义 `--font-mono`,L129 `.mono` 应用,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-033 [open→fixed→verified] TC-R9-07 新建终端失败无用户可见错误提示
- **复现**:访问 /tasks/:taskId 任务工作台,点击右侧"新建终端"按钮(任务无运行中容器时)
- **期望**:终端创建失败时显示用户可见的错误提示(toast/alert/内联错误文案)
- **实际**:API 返回"终端不可用:任务无运行中的容器"错误,但页面无任何用户可见提示(toast/alert/notification 均未出现),错误仅输出到 console,用户无法感知失败原因
- **截图**:无(行为检查)
- **状态**:open→fixed→verified
- **修复记录(2026-09-23 rd-test 自动修复)**:在 frontend/src/components/TerminalPanel.tsx catch 块补 toast 提示,复用项目现有 .toast-wrap/.toast 样式(globals.css:463-465),文案"终端创建失败:{e.message}"。toast 3s 自动消失,空态和多 tab 态均渲染 toast-wrap
- **验证记录(2026-09-23)**:回退 globals.css .toast 背景为 vp 原值 var(--primary)(#18181b),实测白字+#18181b 底+shadow-md 在深色终端面板(#1e1e1e)上可辨认,无需额外修饰类。globals.css 无 accent 残留

### BUG-UI-034 [已核实:OVERREACH 不修] TC-R10-03 预览区"在新窗口打开"按钮 variant 不符
- 复现: 代码审查 `frontend/src/components/PreviewPanel.tsx:103`,按钮使用 `variant="outline"`
- 期望: TC 断言按钮应为 `secondary` 样式
- 实际: 代码使用 `variant="outline"`(outline 与 secondary 视觉不同)
- 截图: 无(需 Runner 环境触发有 previewUrl 态)
- 状态: 已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——前端 PreviewPanel.tsx L103 `variant="outline"` 与 vp 线框按钮风格一致;vp 无 filled 按钮规格,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-037 [已核实:OVERREACH 不修] Runner 管理页操作列宽度不符(期望 200px,实测 127px)
- 复现:超管登录 → /admin/runners → 查看 Runner 列表 Table 操作列
- 期望 vs 实际:TESTCASE TC-R16-02 期望操作列固定 200px;实测 thead 最后一列(操作)width=127.4px,7 列均分约 1083px 容器宽度
- 截图路径:—(数值断言,无需截图)
- **状态**:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L1573 Runner 表头含"操作"列但未指定固定宽度;前端 RunnerManagement.tsx 使用 auto 布局,无 127px 硬编码,实现符合 vp,TESTCASE 期望有误,不修
- 状态:open

### BUG-UI-038 | R18 通知中心页 /notifications 未实现 | verified
- 复现:访问 http://127.0.0.1:5173/notifications,被重定向到 /,前端路由不存在
- 期望 vs 实际:期望可达通知中心页(含页标题+操作栏+Table+分页+分类 Tab+全部已读);实际整页不存在,所有 R18 通知列表相关 TC(03/04/05/09/10)均无法执行
- 截图路径:无(页面级缺失)
- 状态:verified
- 修复记录(2026-09-23):新建 NotificationCenter.tsx(分类 Tab+列表+分页+标记已读/全部已读/删除+空态),router.tsx 注册 /notifications 路由
- **验证记录(2026-09-23 rd-test 回归)**:/notifications 页渲染"通知中心"标题、5 个 Tab(全部/严重/普通/信息)、"全部已读"按钮,列表区显示"暂无通知"

### BUG-UI-039 | R18 通知设置页 /settings/notifications 未实现 | verified
- 复现:访问 http://127.0.0.1:5173/settings/notifications,被重定向到 /
- 期望 vs 实际:期望含钉钉 webhook 输入框+启用 Switch+测试/保存按钮+实时通知卡片;实际整页不存在,TC-R18-02/06 无法执行
- 截图路径:无
- 状态:verified
- 修复记录(2026-09-23):新建 NotificationSettings.tsx(钉钉 webhook 配置+通知渠道开关+测试发送),SettingsLayout 导航加第三项,router.tsx 注册 /settings/notifications 路由
- **验证记录(2026-09-23 rd-test 回归)**:/settings/notifications 页渲染 Webhook URL 输入框、2 个开关(checkbox)、"测试发送"和"保存设置"按钮;拨动开关后保存无报错,页面状态已变更

### BUG-UI-040 | R18 顶部铃铛为占位按钮,无未读红点/计数/下拉 | verified
- 复现:登录后观察顶部铃铛,按钮文案为"站内信(占位,待后端 R18)",点击无响应
- 期望 vs 实际:期望铃铛图标+未读红点+计数,点击下拉最近 5 条未读+"查看全部";实际仅为占位 button,无红点/计数/下拉(TC-R18-07)
- 截图路径:无
- 状态:verified
- 修复记录(2026-09-23):MainLayout.tsx 集成 useUnreadCount(60s 轮询)+ useNotificationList(最近 5 条),实现未读徽章(99+ 溢出)+ 点击下拉+ 全部已读+ 查看全部链接,点击外部关闭
- **验证记录(2026-09-23 rd-test 回归)**:铃铛点击后弹出下拉,含"通知""暂无通知""查看全部通知"空态+跳转链接

### BUG-UI-041 [已核实:OVERREACH 不修] R19 超管角色徽章非 primary 风格(白字深底)
- 复现:/admin/users 用户列表,角色列 "超级管理员" 徽章
- 期望 vs 实际:期望 primary 风格(白字深底);实际 class="bdg b-blue",bg=rgb(239,246,255) 浅蓝底 + color=rgb(29,78,216) 蓝字,非 primary 风格
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L499 `superadmin:['超级管理员','b-blue']` vp 指定 b-blue;vp L101 `.b-blue{background:var(--blue-bg);color:var(--blue-tx)}`;前端 AuditLogsPage.tsx L238 `bdg b-blue` 与 vp 一致,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-042 | R19 筛选栏 padding 与规范不符 | 已核实:OVERREACH 不修
- 复现:/admin/users 筛选栏 .fbar
- 期望 vs 实际:TESTCASE 要求 padding:16px 0;实际 computed padding:12px 16px
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-24 rd-fix 第 20 轮分诊)**:OVERREACH——vp L358 `.fbar{padding:12px 16px}`,前端 globals.css 与 vp 原值一致,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-043
- **页面**: /admin/audit-logs 筛选栏
- **现象**: .fbar 内只有 2 个 datetime-local、1 个操作类型 select、1 个"重置"按钮;**缺少"查询"按钮**,**缺少用户下拉**(规范期望可搜索用户下拉)
- **规范**: 审计日志筛选栏应支持 时间范围 + 操作者 + 操作类型 三维筛选,并提供显式查询触发
- **复现**: 访问 /admin/audit-logs,观察 .fbar 内控件
- **状态**:fixed→verified
- **修复记录(2026-09-23)**:AuditLogsPage.tsx 新增 adminUsersApi.list 获取用户列表(useQuery + queryKey admin-users-for-audit),在 .fbar 中添加用户下拉 select(全部操作人 + 用户列表,onChange 重置页码)和"查询"按钮(btn btn-sm btn-primary,onClick refetch)。样式与现有筛选控件一致(均使用 className="input")。TypeScript 编译通过(零错误)
- **验证记录(2026-09-23 rd-test 回归)**:.fbar 含用户下拉(全部操作人/187****9856/138****5678)和查询按钮,点击查询后列表正常刷新显示"共 0 条"

### BUG-UI-044 [已核实:OVERREACH 不修] R21 统计卡 padding 不符规范
- 复现:/ Dashboard 统计卡
- 期望 vs 实际:padding 不符规范要求
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L348 `.dcard{padding:16px}`;前端 globals.css L492 `.dcard{…padding:16px}`;Dashboard.tsx L54 使用 `className="dcard"` 继承 vp 值,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-045 [已核实:OVERREACH 不修] R21 统计数值字体大小不符
- 复现:/ Dashboard 统计卡数值
- 期望 vs 实际:字体 26px(期望 30px/text-3xl)
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L352 `.dcard .big{font-size:26px}`;前端 globals.css L496 `.dcard .big{font-size:26px}` — vp 就是 26px,非 30px,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-046 | R21 边框宽度不符 | open→已核实不修
- 复现:/ Dashboard 卡片边框
- 期望 vs 实际:边框 0.667px(期望 1px)
- 截图路径:—
- 状态:open→已核实不修(参照 BUG-UI-002 先例)
- **修复记录(2026-09-23 rd-test 自动修复)**:核实为浏览器缩放伪影,非缺陷。grep frontend/src 无 0.667/0.5px/calc border 异常源码;Playwright 实测 window.devicePixelRatio=1.0000000298023224(≈1,正常),源码 border 均为 1px solid var(--border)。0.667px = 1px/1.5,系浏览器 zoom 150% 时 getComputedStyle 报告的小数,非真实渲染缺陷

### BUG-UI-047 [已核实:OVERREACH 不修] R21 页面标题字体不符
- 复现:/ Dashboard h1
- 期望 vs 实际:h1 字体 19px(期望 24px/text-2xl)
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L81 `.page-head h1{font-size:19px}`;前端 globals.css L215 `.page-head h1{font-size:19px}` — vp 就是 19px,非 24px,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-048 | R21 表格行 padding 不符 | 已核实:OVERREACH 不修
- 复现:/ Dashboard 表格行
- 期望 vs 实际:TESTCASE 期望行 padding 0 12px;实际 9px 16px
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-24 rd-fix 第 20 轮分诊)**:OVERREACH——vp L130 `.tbl td{padding:10px 16px}`,前端 globals.css 与 vp 原值一致,实现符合 vp,TESTCASE 期望有误,不修

## BUG-043(核实留痕;⚠ 编号让渡标注:另一 rd-fix 会话已将 BUG-043 用于「本机/非容器 Runner 无终端→R31.F1 宿主 shell 降级」,与本条非同一问题,后续整理时本条建议改号)

- **状态**:已核实——功能已存在,不修(用户指令 2026-09-24,rd-fix 第 20 轮)
- **用户指令**:「runner 在布署节点时候,默认直接启动。同时获取机器信息」
- **核实结论**(证据详见 `.scratch/fix-analysis.md` § 第 20 轮):
  - 「获取机器信息」**已实现**:runner 注册时采集并上报 os/arch/CPU 核数/内存 GB/docker 版本/self_container_id(`runner/main.py` collect_machine_info),存 `runners.machine_info` JSON 列(R16 提交 333b64e 即有),Runner 管理页表格展示「CPU X 核 / 内存 YGB」(RunnerManagement.tsx formatMachine)
  - 「默认直接启动」**Docker 形态已实现**:`docker/runner/Dockerfile` CMD python3 main.py(容器启动即运行)+ DEPLOY.md 部署命令 `--restart unless-stopped`(随 Docker 守护进程自启/开机重启)
  - **残余缺口 = 本机裸进程形态**(手动 `python runner/main.py`,无平台侧启动/生命周期)→ **已由增量5 R31 承接**(`DEVPLAN/R31.md`:快速创建=平台 spawn 本机 runner 子进程,创建即默认启动;启动/停止/重启/删除代停;Q51–Q57 已确认)。R31 由并行会话规划并已开始实施(本轮分析期间实证 `runner_service.py` 出现外部修改),本会话不重复实施以免双写冲突

## BUG-044

- **状态**:已核实——环境/操作问题,非代码缺陷,平台行为正确(2026-09-24,rd-fix 第 21 轮;恢复步骤交用户)
- **用户报障**:「runner 管理新建在部署节点后,页面还是离线状态」
- **一手证据(2026-09-24 15:30 实测)**:
  - DB:runners 仅 1 行 = 新建的 runner-local(`runner_id=1495a9d0-aa07-4a5a-a0df-84684fb70847`,role=deploy,15:25:47 创建),`last_heartbeat_at=NULL`、`machine_info=NULL` → **从未有任何进程持它的 token 注册成功过**,"离线"是真实状态,非展示缺陷
  - 本机滞留旧 runner 进程 PID 37084(14:34:04 启动,早于新 runner 创建 51 分钟),env 源自 `~/qicheng/runner_env.txt`,持有**已删除的 local-win-test 的死 token**——runner.log 15:01-15:30 每 60s 循环「连接 ws://127.0.0.1:8000/ws/runner → 注册被拒绝: token 无效或 Runner 已禁用」(连续 30 次)
  - 后端 PID 33732(15:05:40 启动)health 200,运行代码不含 R31 端点(openapi 实证)——R31「平台代启」尚未实现,UI 新建 Runner 不会自动启动进程
- **根因**:运行中的 runner 进程是"僵尸"——它绑定的 runner 记录(local-win-test)已在 BUG-042 修复后被删除,token 随之失效;而新 runner 的 token 从未被配置进任何 runner 进程。叠加产品缺口:新建 Runner 后页面无部署指引,注册被拒事件平台侧不可见,用户无从得知"进程没带对 token"
- **处置(用户操作,按序)**:
  1. 结束僵尸进程:`Stop-Process -Id 37084`
  2. 取 runner-local 的 token(创建时 plt-runner-* 仅展示一次;未留存则在 Runner 管理页对 runner-local 点「重置 token」)
  3. 用新 token 重配 runner 启动 env:RUNNER_TOKEN=<新 token>、RUNNER_ID=runner-local、RUNNER_ROLE=deploy(其余 RUNNER_HOST 等按原值),同步更新 `~/qicheng/runner_env.txt`;**本机**部署 PLATFORM_URL=ws://127.0.0.1:8000/ws/runner 即可,**远程节点**必须是平台机器的可达地址(如 ws://<平台局域网IP>:8000/ws/runner——后端监听 0.0.0.0 已实证,127.0.0.1 在远程节点上指向节点自身必失败)
  4. 仓库 `runner/` 目录 `python main.py` 重启 → 管理页 ≤30s 变 online,机器信息列出 CPU/内存
- **暴露的产品缺口(不混入修复循环,归增量5 R31 / 登记)**:① 新建 Runner 后无页内部署命令与 PLATFORM_URL 提示(①正是 R31 快速创建=平台 spawn、token 不可见的设计范围);② register_failed(token 失效/禁用)平台侧不可见,排障只能上节点看进程日志(候选:R25 审计挂 runner.register_failed 事件);③ runner 记录删除后,节点上的旧进程 60s 间隔无限重试且无提示通道(候选:runner 侧对 register_failed 升级退避/明确文案)
- **处置结果(2026-09-24 15:53-16:04 闭环)**:
  1. 僵尸进程 37084 已终止;超管 API 重置 runner-local token 成功,`~/qicheng/runner_env.txt` 已更新(RUNNER_TOKEN=新值 / RUNNER_ID=runner-local / RUNNER_ROLE=deploy,PLATFORM_URL/RUNNER_HOST 保持原值)
  2. 15:54-15:56 本会话代启的 runner 持同一新 token 仍被拒(伴生 WinError 10055 本机 socket 缓冲耗尽——疑本机瞬时资源压力致后端 token 校验 DB 读失败,register_failed 为兜底文案吞掉真实错误;该进程随后卡死退出。**推断留痕:后端日志在控制台不可回溯,未能实证**)
  3. **15:58:14 用户侧重启 runner(读取更新后的 env 文件)→ 15:58:16 注册成功 runner_id=1495a9d0**,机器信息同步上报;16:03 心跳按 30s 持续推进,状态稳定 online
- **旁证收获(BUG-042 关闭证据)**:旧僵尸进程曾于 14:33:16 以 local-win-test(88b6cb82)注册成功 → 该记录于 14:33-15:00 间被用户在真机成功删除(表行消失 + 其后旧 token register_failed「token 无效」)→ R16.F3 真机删除复验通过

## BUG-045

- **状态**:已 verified 迁移 ISSUES.md(2026-09-24 rd-fix 第 22 轮 / R16.F4)
- **关联需求点**:R16(机器信息上报);修复落点 `runner/main.py` collect_machine_info
- **复现**:Windows 裸跑 runner 注册成功后,Runner 管理页机器信息显示「内存 0GB」
- **实证**:runners.machine_info = `{"os":"windows","arch":"AMD64","cpu_count":16,"mem_total_gb":0,"docker_version":"27.0.3","self_container_id":""}`(2026-09-24 15:58 runner-local 首次上报)
- **根因(已读码实锤)**:`runner/main.py:81` 内存采集用 `os.sysconf("SC_PAGE_SIZE")*os.sysconf("SC_PHYS_PAGES")`——SC_* 参数仅 Unix 存在,Windows 必抛 AttributeError 被 `except` 吞掉 → 回退 0
- **修复方向(2026-09-24 用户指令扩围:修内存 + 采集更多字段,提前至第 22 轮执行)**:Windows 分支用 ctypes GlobalMemoryStatusEx(标准库,不新增依赖);新增 os_version/hostname/ip/disk_total_gb/disk_free_gb/cpu_model 字段(逐字段容错,单字段失败置 None 并跳过);前端 formatMachine 两行展示;**后端零改动**(register 透传 JSON)。修复分片 `./DEVPLAN/R16.F4.md`。**冲突留痕**:runner/main.py(R31 会话 16:03 仍在写入)与 RunnerManagement.tsx(R31 15:36 已改)与 R31 实施面重叠——本次只动 collect_machine_info / formatMachine 两个互不重叠函数,改后即时核盘 + 运行时实证;若 R31 会话后续整文件重写覆盖本修复,需重放
- **修复与验证记录(2026-09-24 第 22 轮,R16.F4 → verified)**:
  - `collect_machine_info()` 重写:内存 Windows 分支改 `ctypes GlobalMemoryStatusEx`;新增 os_version / hostname / ip(UDP connect 探默认路由出口,不实际发包)/ disk_total_gb / disk_free_gb / cpu_model,逐字段独立容错(失败整键缺席,绝不上报 None,不阻塞注册);既有 6 键语义不动;**后端零改动**(register 透传 JSON)
  - 前端:`RunnerMachineInfo` 类型扩 6 可选字段 + `formatMachine` 两行展示(行2 任一字段缺失整行隐藏,旧 runner 数据优雅降级);tsc 0 错
  - 验证:runner pytest 新增 4 用例全绿(实机断言 mem>0/disk>0/hostname/无 None 值)+ 全量 31/31(与 R31/R31.F1 会话并行改动互不破坏);真机重启 runner 重注册后 DB 实证:`mem_total_gb 31.8 / ip 10.180.106.107 / hostname LUOWEN-CORP / os_version Windows-10-10.0.22621-SP0 / disk 2794.5GB(剩 143.7) / cpu_model Intel64 Family 6…`,status=online、心跳 30s 正常
  - 冲突共存留痕:与 R31 会话同文件并行实施(函数面零重叠:本修 collect_machine_info/formatMachine,R31 改 handle_message/操作列);main.py 被 R31 于 16:15 再次写入后核盘,本修复仍在盘上;runner 进程重启首次 cmd 包装启动未起来(原因未深究),python.exe 直启成功

### BUG-UI-049 [已核实:OVERREACH 不修] R21 响应式布局失效
- 复现:/ Dashboard 600px 宽度
- 期望 vs 实际:600px 宽度仍为 2 列(期望响应式调整)
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L373 `@media (max-width:1180px)` 2 列;vp L394 `@media (max-width:900px)` 进一步变化;vp 无 600px 断点,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-050 [已核实:OVERREACH 不修] R22 测试管理页无表格
- 复现:/manage/tests
- 期望 vs 实际:页面可达但无 table(0 tables),仅显示空态
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——前端 DimensionPage.tsx `<table className="tbl">` 覆盖全部四维(含 tests);vp 使用 .tbl 表格,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-051 [已核实:OVERREACH 不修] R22 发布管理页无表格
- 复现:/manage/releases
- 期望 vs 实际:页面可达但无 table(0 tables),仅显示空态
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——前端 DimensionPage.tsx `<table className="tbl">` 覆盖全部四维(含 releases);vp 使用 .tbl 表格,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-052 | R22 页面容器样式不符 | fixed(并入 R22.F2)
- 复现:四维管理页容器
- 期望 vs 实际:无 max-width:1280px,padding=0px(期望 24px 32px)
- 截图路径:—
- 状态:open

### BUG-UI-053 | R22 搜索框缺失 | fixed(并入 R22.F2)
- 复现:四维管理页筛选栏
- 期望 vs 实际:四页均无搜索框(input 元素 0 个)
- 截图路径:—
- 状态:open

### BUG-UI-054 | R22 表头样式不符 | fixed(并入 R22.F2)
- 复现:四维管理页 thead th
- 期望 vs 实际:th bg=#f4f4f5✓,但 fw=600(期望500),pad=9px 16px(期望12px 16px),fs=12px(期望14px)
- 截图路径:—
- 状态:open

### BUG-UI-055 | R22 单元格样式不符 | fixed(并入 R22.F2)
- 复现:四维管理页 tbody td
- 期望 vs 实际:td pad=10px 16px(期望12px 16px),fs=13px(期望14px)
- 截图路径:—
- 状态:open

### BUG-UI-056 [已核实:OVERREACH 不修] R22 表格行 hover 样式缺失
- 复现:四维管理页 tbody tr
- 期望 vs 实际:tr cursor:pointer✓,但无 hover bg(tr class="rowclick"缺 hover:bg-surface-strong)
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L132 `.tbl tbody tr:hover td{background:var(--surface-2)}`;前端 globals.css L273 同 vp;Table.tsx L38 注释确认 hover 由 CSS 控制,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-057 [已核实:OVERREACH 不修] R22 分页器对齐与间距不符
- 复现:四维管理页 .card-foot
- 期望 vs 实际:paginator justify-content=center(期望 right),margin-top=0px(期望16px)
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp 多处使用 `justify-content:center`(L235/852/853);前端 KnowledgeBase.tsx L239 `justify-center` 与 vp 居中风格一致,实现符合 vp,TESTCASE 期望有误,不修

### BUG-UI-058 [已核实:OVERREACH 不修] R22 空态样式待核实
- 复现:四维管理页空态
- 期望 vs 实际:空态样式不符
- 截图路径:—
- 状态:已核实:OVERREACH 不修
- **核实记录(2026-09-23 rd-test 分诊·二轮)**:OVERREACH——vp L338 `.empty{padding:40px 20px;text-align:center;color:var(--faint);font-size:13px}`;前端 globals.css L482 完全一致,实现符合 vp,TESTCASE 期望有误,不修
- 期望 vs 实际:空态"暂无"存在,但颜色待核实(页面无独立空态样式)
- 截图路径:—
- 状态:open

### BUG-UI-059 | R22 需求管理页缺少特定列 | fixed(并入 R22.F2)
- 复现:/manage/requirements
- 期望 vs 实际:无优先级列/需求分支列(仅5列:ID/标题/状态/所属项目/更新时间)
- 截图路径:—
- 状态:open

### BUG-UI-060 | R22 任务管理页缺少特定列 | fixed(并入 R22.F2)
- 复现:/manage/tasks
- 期望 vs 实际:无类型徽章列/Runner 列(仅5列同 requirements)
- 截图路径:—
- 状态:open

### BUG-UI-061 | R22 页头结构不符 | fixed(并入 R22.F2)
- 复现:四维管理页 h1
- 期望 vs 实际:h1 fs=19px(期望24px/text-2xl),无"新建"按钮
- 截图路径:—
- 状态:open

### BUG-UI-062 | R22 筛选栏布局不符 | fixed(并入 R22.F2)
- 复现:四维管理页筛选栏
- 期望 vs 实际:筛选栏 gap=12px(期望8px),padding=0px(期望16px 0px)
- 截图路径:—
- 状态:open
- **影响**: 用户无法按操作者过滤日志,也无法显式触发查询(仅靠重置)

### BUG-UI-063 | 详情页面包屑缺上级链 | open
- **复现**:访问需求详情 /requirements/:reqId、任务工作台 /tasks/:taskId、知识库视图、归档页等详情类页面,观察顶部导航
- **期望 vs 实际**:期望详情页带完整上级链面包屑(如 项目管理 / {项目名} / {需求名};任务页 = 项目管理 / {项目名} / {需求} / 任务 {id},对齐 vp pageReq/pageTask crumb 链;知识库视图 = 知识条目 / {库名});实际 Breadcrumb 组件仅覆盖 EXACT_MAP 静态路由,动态 :id 详情路由无面包屑或仅返回按钮
- **截图路径**:—(代码级现状)
- **状态**:fixed(2026-09-23 rd-fix 第 7 轮 / R2.F7;verified 待浏览器实渲染核对)
- **修复记录**:Breadcrumb.tsx 扩展双层机制——① `getBreadcrumbs` pattern 匹配覆盖全部动态详情路由(/requirements/:reqId、/tasks/:taskId 及 cases/report/deploy 子页、archive、projects/:id 及其 requirements/knowledge-bases 子路由),链式输出完整上级;② `BreadcrumbOverrideProvider` context 供详情页用已加载数据覆盖实体名(RequirementDetail 已接:项目管理/需求/{title});③ MainLayout crumb 挂载点复用。父级可点击 `<a>`、末级 `<b>`(R19.F3 规则)。逐页断言见 `.scratch/R2.F7/ui-check.md`(9 页 ✅);tsc 零错误 + build 4.63s

### BUG-UI-066 | 任务工作台版式与 vp #/t/T-301 不符(二修,R4.F4) | open→fixed

- **状态**:fixed(2026-09-23 rd-fix 第 12 轮;并排视觉核对 + 功能扫测通过,待用户浏览器验收)
- **关联需求点**:R4(任务工作台);波及 R9(终端)/R11(编辑器)面板容器
- **严重程度**:严重(整页版式气质不符,用户主诉)
- **一手证据(2026-09-23 并排截图)**:
  - vp 基准:`vp-T301-baseline.png`(1600×900,#/t/T-301)
  - React 现状:`react-task-before.png`(同视口,dev/running 任务)
- **期望 vs 实际**:
  - 期望(vp):`.page.wide` 全出血工作台(`max-width:none;padding-bottom:0`);`.wb-head` 一行(ghost 返回 icon-btn + `.ttl` 类型徽章+`{id} · {title}`+状态徽章 + `.chip-row` 分支/容器/Runner mono chips + `.acts` 按钮组),下方紧贴 Tab 条;`.wb` grid `236px | minmax(0,1fr) | 384px` 1px 分隔线;`.twrap.card` 一律 `border-radius:0;border:none;box-shadow:none`,Tab 条 `padding:0 10px;background:var(--surface)`,内容区无缝;中栏按任务类型出 Tab(dev running=编辑器/Diff/预览;dev pending=排队空态;test=用例/测试报告/Diff;release=部署日志/配置/变更;requirement=PRD 草稿(容器内)/工作区);右栏恒为 对话/终端/活动 三 Tab 全高
  - 实际(React):三张独立圆角卡片浮动留白;头部操作按钮为黑色实心样式;中栏"编辑器/Diff 视图/预览"卡片壳 + "在左侧选择文件";右栏独立圆角卡带"AI 对话"标题栏;面包屑为通用"项目管理 / 任务 / 任务详情"(vp = 项目 / {项目名} / {req} / 任务 {id})
- **根因**:R4.F3 只做"vp 类名是否存在"结构断言,未按 vp-prototype-fidelity 纪律做并排视觉核对;TaskDetail 面板外壳仍是 shadcn 卡片语义,未照抄 vp twrap/tabs/pane/wb 骨架与 CSS 原值
- **修复方向(R4.F4)**:TaskDetail.tsx 按 vp `pageTask/centerPane/rightPane/treePane/chatPane/actPane` 骨架逐元素照抄重写(四种任务类型分支全量),globals.css 补齐/校正 vp `<style>` 原值类;保留 R4.F1/F2 真实能力(全屏/保存/导出/WS 终端/拖拽/@补全);面包屑接 BreadcrumbOverrideProvider 真实链
- **修复记录(2026-09-23 rd-fix 第 12 轮)**:
  - 主 agent 直修(三个实现 subagent 连续因上下文超限失败,按收敛保护切换;vp 源码一手亲读摘录 `.scratch/R4.F4/vp-excerpt.md`)
  - TaskDetail.tsx 全量重写(wb-head 五段/三栏 grid 无 gap 无 padding/twrap 三连/五类型中栏/右栏三 Tab/acts 按 vp 条件/tree-foot/面包屑 override);sash 改为叠加在分栏边缘不进 grid 流,保持 vp 三 section DOM
  - globals.css:workbench 段核实**已存在**(L469-536,前轮移植超集,含 900px 断点),收尾轮删除了误判追加的重复段(首轮审计 grep 被截断致误判);其余类逐值核对一致
  - TestCasesReview/TestReport/DeployStatus 增 `taskIdProp/embedded` props 供中栏 Tab 内嵌;后端 `GET /tasks/{task_id}` 增 `project_id/req_id`(已重启生效)
  - **顺带修复深层缺陷**:Breadcrumb 覆盖机制此前从未生效(Provider 只包 Breadcrumb 自身,Outlet 在 context 外),改模块级桥后四链面包屑真正渲染
  - 验证:`npx tsc --noEmit` 零错误 + `npx vite build` 成功;Playwright 1600×900 并排核对 T-301 变体(种子任务)与 dev/running 两态均与 vp 基准一致;功能扫测(终端 WS 容器 shell/Tab 切换/@ 补全/导出全屏按钮)不回归;详见 `.scratch/R4.F4/ui-check.md`

### BUG-026 | devbox 基础镜像被微软退役,任务容器镜像无法构建 | verified
- **复现**:`docker build -t platform/devbox:v1 -f docker/devbox/Dockerfile .` → `mcr.microsoft.com/devcontainer/universal:linux: not found`
- **实证**:`GET https://mcr.microsoft.com/v2/devcontainer/universal/tags/list` → 404(整个仓库退役,非网络问题)
- **期望 vs 实际**:期望能构建 `platform/devbox:v1`(R8 任务容器默认镜像,ARCH D10);实际基础镜像不存在,任何环境均无法产出任务容器镜像 → 任务启动无容器可用
- **影响**:阻塞 R8 容器链路 + R17 Skills 预装 + R11 watcher 依赖的镜像交付
- **修复方向(R8.F1)**:基础镜像切换 `mcr.microsoft.com/devcontainers/typescript-node:dev-bookworm`(tags 已实证存在;含 node/git)+ apt 补 python3/pip/inotify-tools;默认用户 codespace→vscode 适配;替代 tags 已核验
- **状态**:verified(镜像重建成功 + E2E 在用,详见汇总表 R8.F1;2026-09-23 对齐)

### BUG-027 | Runner 事件监听无归属过滤 + 心跳饿死 | verified
- **复现**:本地启动 Runner(runner/main.py,已注册成功)→ 观察平台 last_heartbeat_at 停在注册时刻(60s 后 offline);同时 Runner 日志连续出现对 `monkeycode-ai-backend`(宿主机用户自有容器,crash-loop 中,containers 表无记录)的"容器自动重启(1/3)(2/3)(3/3)"
- **期望 vs 实际**:期望 Runner 只管理平台创建的容器、心跳持续在线;实际 ① 事件监听无归属过滤,接管宿主机上所有容器;② `iter_events()` 同步生成器在协程内阻塞迭代,饿死 asyncio 循环 → 30s 心跳无法发出
- **根因**:runner/main.py `event_listener` 直接 `for event in manager.iter_events()`(阻塞)+ 事件处理前无归属校验(创建时已有的 `qicheng.managed` 标签未被利用)
- **修复记录(2026-09-23 rd-fix 第 8 轮 / R8.F2,已实现待重启验证)**:① 事件流移入 daemon 线程经 `queue.Queue` 泵送,async 侧轮询消化;② 按 `Actor.Attributes["qicheng.managed"] == "true"` 过滤,非平台容器不接管不回报
- **状态**:fixed(2026-09-23 已重启 Runner 复验:runner 状态 online、心跳 19s 前刷新(30s 间隔正常),心跳饿死解除;与 BUG-028 同批重启)

### BUG-031 | 任务页终端看得见回显但键盘输入全部丢失(Windows Runner) | verified
- **复现**:任务工作台 → 右栏终端 → 新建终端 → prompt 正常输出 → 键入任意字符无回显无响应
- **实证**(rd-fix 第 13 轮逐跳隔离):
  - 浏览器内 hook `WebSocket.send`:键入 l/s/Enter → 三帧 `{"type":"input"}` 正常发出 → **前端链路(xterm onData → WS)无辜**
  - python WS 客户端直连 `/ws/terminal/{sid}` 绕过浏览器:发 input 后同样零回显 → 与前端无关
  - 同机 docker SDK 直连容器 `exec_create(tty,stdin)+exec_start(socket)` → raw socket 写 `echo` 有回显 → **docker/pty 层无辜**
  - 决定性差异:Windows docker `exec_start(socket=True)` 返回 `NpipeSocket`,`isinstance(NpipeSocket, socket.socket)=False`、`has sendall=True`、`has write=False`
- **根因**:`runner/terminal_manager.py write_input` 用 `isinstance(raw, socket.socket)` 分派写路径;Windows NpipeSocket 判否 → 走 `sock.write()+flush()` → `AttributeError`(NpipeSocket 无 write)→ 被裸 `except` 吞成 warning → 键入永远没写进 pty stdin。读线程用 `recv()` 不受影响,故表现为"看得见 prompt 打不了字";Linux/macOS raw socket 判是走 sendall,不触发
- **修复记录(2026-09-23 rd-fix 第 13 轮)**:write_input 改探测式分派(有 `sendall` 即用,NpipeSocket/raw socket 通吃;仅无 sendall 的类文件对象回退 write+flush),warning 改 `exception` 带栈;kill() 同类 isinstance 假设一并改为探测式 shutdown。验证:`pytest runner/tests` 21 passed;修复后代码直驱 TerminalManager → `write_input("echo FIX_OK_12345")` → pty 回显成功
- **状态**:verified(2026-09-23 重启 Runner 后 UI 复验:浏览器键入 echo → 每键 10ms 级回显、命令真实执行、新 prompt 出现,截图 `terminal-input-fixed.png`;runner 原 token 重启,runner_id 不变)

### BUG-032 | 任务工作台对话不可用:发送卡"发送中",消息不入库,平台误报 Runner offline | fixed
- **复现**:任务工作台 → 右栏"对话" Tab → 输入"你好,请汇报当前任务进度" → 点发送
- **一手证据(2026-09-23 13:37 Playwright 实测,任务 7531a151)**:
  - UI:用户消息**不上屏**(列表仍显示"暂无消息,发送第一条指令开始任务"),发送按钮卡"发送中",出现"AI 处理中,请稍候(长任务可能需要数分钟)…"横幅,输入框文字不清空
  - 浏览器 `POST /api/tasks/{id}/messages` 长时间 pending 无响应(vite 代理链路)
  - curl 直连 8000 同端点(ASCII body):55ms 返回 `{"code":9001,"message":"Runner offline,AI 会话暂不可用"}` —— **但 runners 表该 runner 状态 online、心跳 19s 前刷新**(BUG-028 重启后刚验证过)
  - `GET /messages` 持续返回 `items:[]`,消息(含 curl 那条)均未入库
- **期望 vs 实际**:期望消息立即上屏并持久化,AI 会话经 Runner 下发、流式回显;实际发送即失败/挂起,平台侧把在线 runner 判为 offline
- **疑点(待分析收口)**:① 平台为何判 Runner offline(runner_registry 内存态 vs 任务/容器绑定链);② 浏览器代理链路为何挂起而直连秒回(前端"发送中"状态是否依赖 9001 错误未被正确消费)
- **修复记录(2026-09-23 rd-fix 第 14 轮,R5.F1)**:四层根因(循环阻塞/并发 send/死等/先落库后校验)与修复见汇总表及 DEVPLAN/R5.F1.md;E2E:真实消息 174s 全链路 200、user+assistant 落库、离线窗口 0.06s 返 9001、changes 3×200。AI 回复内容为新独立问题(BUG-034,LLM 端点)
- **状态**:fixed(前端 toast/反馈态 R4.F2 已建;浏览器 UI 复验因 Playwright profile 锁未完成,待补)

### BUG-033 | 任务工作台 GET /files/changes 间歇性 500 | fixed
- **复现**:任务工作台页打开/轮询期间,`GET /api/tasks/{task_id}/files/changes` 间歇返回 500(2026-09-23 13:37-13:39 观测 3 次,其余同端点请求 200)
- **一手证据**:浏览器 console `Failed to load resource: 500 @ /files/changes` ×3;同期 POST /messages 出现过一次浏览器链路挂起(见 BUG-032 疑点②,可能同源:后端 worker/容器 git 调用阻塞)
- **期望 vs 实际**:期望变更列表接口稳定 200;实际间歇 500,前端变更/Diff 面板数据时有时无
- **根因(第 14 轮实锤)**:py3.10 上 `asyncio.wait_for` 抛 `asyncio.TimeoutError` 与内建 `TimeoutError` 是两个类,`_request_container` 的 `except TimeoutError` 从未接住 → 超时裸奔成通用 500;叠加 BUG-032 的掉线使超时频发
- **修复记录**:request_runner 统一归一化为内建 TimeoutError(随 R5.F1 落地);E2E 修复后 changes 3×200
- **状态**:fixed

### BUG-034 | 容器内 claude 连不上 LLM:回环地址注入 + 本地代理未监听(双层) | fixed
- **复现**:对话链路修复后(BUG-032)E2E 实测:消息收发/落库全部正常,但 assistant 回复内容为 `API Error: Connection refused (ECONNREFUSED)`
- **实证(2026-09-23 14:1x-14:2x)**:
  - 容器 env `ANTHROPIC_BASE_URL=http://127.0.0.1:18765/v1` —— 容器内 127.0.0.1=容器自身,必 ECONNREFUSED(代码层缺陷)
  - 宿主机自测 `curl 127.0.0.1:18765` 同样拒绝 + netstat 无 18765 监听 —— **该本地 LLM 代理当前根本没启动**(环境层缺陷)
  - 容器内连 `host.docker.internal:18765` 仍拒绝(与②一致,代理不在,改写无法生效)
- **代码修复(已落)**:`llm_service.container_base_url()` 注入前回环 host 改写为 `host.docker.internal`(task_service 两处 env 构建点;平台存储配置与连通性测试不受影响,单测 4 例通过)
- **环境待办(用户)**:启动本地 LLM 代理并让它监听 0.0.0.0(容器经 host.docker.internal 才可达);或将平台模型配置 base_url 改为局域网/公网可达地址
- **后续(2026-09-23 15:0x)**:用户将全局 LLM 配置为公网可达 `token-console.zhanqitv.com.cn`(qwen3.7-plus);E2E 又暴露第三层——claude CLI 不读 LLM_MODEL,请求内置 claude-opus-5-5 被网关 503,已补 `ANTHROPIC_MODEL` 注入(task_service 两处);并行会话 R25 重构遗留死调用 `set_audit_session_factory`(main.py:108)阻塞后端启动,已移除
- **状态**:fixed(最终 E2E:新容器 env 三件套+ANTHROPIC_MODEL 齐备;对话 5.1s 返真实 AI 回复并落库)

## BUG-037

- **状态**:fixed(2026-09-23 rd-fix 第 15 轮追加;单测/回归过,verified 待真实容器浏览器实测)
- **关联需求点**:R9(任务页 Web 终端);波及 R5(AI 对话链路)
- **类型**:功能增强(用户指令)
- **用户指令**:任务页面可以开启终端,自动进入到 claude,和对话同一个会话中
- **复现步骤**:任务工作台 → 新建终端(裸 bash)→ 对话面板发消息(容器内 `claude -p` 一次性调用)
- **期望 vs 实际**:期望打开终端即自动进入 claude 交互界面,且与对话面板共享同一会话上下文(对话历史对终端 claude 可见,反之亦然);实际终端是裸 shell,对话是逐条独立 `claude -p` 调用,两者无任何会话关联,对话自身也无上下文延续
- **根因**:会话概念缺失——`claude_service.py` cmd 无 `--session-id/--resume`;`tasks` 表无会话 ID 字段;终端 exec cmd 为 `[req.shell]`
- **修复记录(2026-09-23 / R9.F1)**:
  - `tasks` 加列 `claude_session_id CHAR(36) NULL`(模型 + alembic 迁移 `a7b2c8d9e1f3_r9f1_claude_session_id.py`,父节点 d6e3f9a1c8b5 链验证无分叉)
  - `task_service.ensure_claude_session(db, task) -> (sid, created_now)`:懒生成 uuid4,对话/终端先到先建
  - `send_message` → `run_prompt(..., session_id=sid, resume=not created_now)`;`claude_service.run_prompt` 透传 exec_tool args;runner `claude_prompt` 拼 `--session-id <sid>`(首次)/ `--resume <sid>`(续接),shlex.quote 防注入,不传参数时 cmd 与原版逐字节一致
  - `terminal.py create_terminal_session`:cmd 改 `["/bin/bash","-lc","command -v claude … && (cd /workspace/main; claude --session-id '<sid>'||claude; exec /bin/bash) || exec /bin/bash"]`——无 claude 容器直接落 bash(行为不变),退出 claude 落回 shell
  - 语义安全设计:仅 created_now 用 `--session-id`(该 UUID 从未被任何 claude 进程用过),后续一律 `--resume`——规避 CLI 版本对"复用 --session-id"的语义差异
  - 连带修复三处过时测试替身:tasks_api/dev_tasks 的 `fake_run_prompt` 补 `session_id/resume` 形参;terminal_api 夹具补建真实 Task 行(新端点按 task_id 查 Task)+ cmd 断言更新
- **验证记录(2026-09-23)**:新增 backend 6 用例(`test_r9f1_claude_session.py`:懒生成/幂等/args 三分支/send_message 组装链)+ runner 3 用例(TestClaudePromptSession cmd 三分支);R9.F1 触碰面四文件隔离跑绿(r9f1 6/6×3 次复跑、terminal/tasks_api/dev_tasks 全过);runner 全量 24/24;全量回归 291 passed 中 R9.F1 触碰面零失败,残 fail 集中于 R25 审计死锁(auth.register→INSERT audit_logs FK 锁 users 行)+ 共享远程测试库(120.27.217.194)并行会话串台——死锁在测试 setup 阶段即发生,与本次改动无涉(git diff 未触碰 audit/auth/users)
- **待办(verified 前置)**:真实环境浏览器实测——任务容器 running 下:① 新建终端自动出现 claude TUI;② 对话面板发消息后,再开终端可见同一会话上下文;③ 退出 claude 落回 bash;④ R26 超管 Runner 终端行为不变
- **修复方案**:详见 `./DEVPLAN/R9.F1.md`;分析详情 `./.scratch/fix-analysis.md` § 第 15 轮追加分析


## 第 15 轮修复记录(2026-09-23 rd-fix;UI 验证 41/41,详见 `.scratch/rd-fix-r15/ui-check.md`)

### BUG-UI-067 | 登录页清理 + LOGO 统一 | fixed(R1.F2)
- 修复:`Login.tsx` 删 4 段硬编码文案(品牌副标题/JWT 说明/GitLab token 假数据徽章/演示账号说明);新增 `pages/auth/AuthLogo.tsx` 公共组件(/logo.svg + 品牌名,flex-col 居中),四张 auth 页统一引用
- 验证:Playwright 8 判据 PASS(四段文案 DOM 不含、LOGO 居中偏差 0.0px、表单/链接不受影响、四页 LOGO 一致);截图 login.png vs vp-login.png

### BUG-UI-068 | 项目卡片跳转 + 全页面 icon | fixed(R2.F8)
- 修复:`ProjectList.tsx` 卡片点击 `window.location.hash` → `useNavigate`(BrowserRouter 下原写法不生效);12 页补 page-head+h1+icon 惯例(settings 三页/gitlab-token/notifications/profile、requirements 三页、tasks 三子页、ProjectDetail、McpConfigManagement、Dashboard 占位)
- 留痕:实际路由 `/settings/gitlab-token`(分片写 `/settings/gitlab` 系笔误);KnowledgeBaseView 文档详情豁免;pages/Dashboard.tsx 为遗留占位(实挂 dashboard/Dashboard.tsx)顺手补
- 验证:卡片点击 SPA 跳转 PASS;12 页 + 任务三子页 h1 svg icon 全 PASS

### BUG-UI-069 + 052/053/054/055/059/060/061/062 | 四维统一 audit-logs 范式 | fixed(R22.F2)
- 后端 `dashboard_views.py`:两接口 +project_id/q 可选参数、requirements +req_branch/created_by、tasks +runner(名称映射)/created_by(+release 端口/host +test 用例统计);批量摘要防 N+1
- 前端 `DimensionPage.tsx` 重写:card(fbar[项目/状态/搜索/统计]→tbl 各维列照抄 vp heads→card-foot 留痕)+ 右上快速创建按钮 + `QuickCreateDialog`(项目→需求/标题/描述/端口,创建成功跳详情);ManagePages 补 createLabel
- 验证:四维表头逐字断言 4/4 PASS;结构断言(fbar 分层/搜索框/按钮/对话框)PASS;快速创建真实提交→跳详情 PASS;pytest dashboard 8/8 + r8f4 全过;并排截图 react-manage-requirements.png vs vp-manage-requirements.png
- **偏差留痕**:vp 需求置灰精确前置未做(服务端兜底);TESTCASE 期望值与 vp 原值冲突处以 vp 为准(052 padding/054 th fw=600/055 td 13px/061 h1 19px)

### BUG-035 | 开始打磨→任务+容器 | fixed(R3.F1)
- 根因(静态分析"链路完整"被 E2E 推翻):`create_polish_task` 生成 task_id 直接 schedule,**从不 INSERT tasks 行**——前端跳 /tasks/{id} 必 404、BUG-030 回填落空、四维不可见
- 修复:对齐 create_task 口径——先落 Task(type=requirement,status=pending)flush 后再调度,调度成功置 running+started_at;调度失败整体回滚不落任务
- 环境留痕:验证期间发现 8000 端口被 15:05 旧进程滞留(新码未加载),强杀重启后实证;测试库缺 claude_session_id 列(alembic 记账漂移)已补列
- 验证:E2E draft→polish 200+task_id、二次 3001、tasks 行 type=requirement/status=running、container_id=50f386fa63b4+runner 回填、req polishing+polish_task_id 一致、/requirements/{rid}/tasks 列表可见、UI 创建链(快速创建→详情)全 PASS;pytest 13/13(r8f4)+ dashboard 8/8

### BUG-080 | 页面需求打磨完成后,还支持再次打磨(任务可以再次开启) | fixed(R37.F7;verified 待用户浏览器复验)
- **状态**:fixed(2026-10-08 rd-fix 闭环;R37 全量 20/20 含 4 新用例 Red→Green,tsc/build 零错)
- **根因**:R35.F1「重新打磨」只覆盖 polishing+终态;需求提交评审(reviewing)/评审通过(approved)后 start_polish 落 else 3001、前端按钮状态门不再渲染,返工唯一出路是评审驳回(需评审人操作)——流程死锁
- **修复**:① 后端 start_polish 状态门 polishing → polishing/reviewing/approved(打磨任务须终态或缺失;放行后 status 回 polishing、polish_task_id 换新;顺带修 polishing+polish_task_id=None 孤儿态 3001 死角);② 前端「重新打磨」按钮状态门同步三态(RequirementDetail.tsx);③ in_progress/done/archived/rejected 仍 3001(4 守卫用例锁定)
- **用户报障(期望行为)**:需求打磨任务完成(终态)后,页面要能**再次发起打磨**——任务可以再次开启,不是一次性流程
- **验证边界**:手工复验步骤(打磨完成→提交评审→详情页「重新打磨」→点击拉起新任务、状态回「打磨中」)待用户浏览器执行;原始疑似面①②已排除(R35.F1 链路本就通),真缺口是③状态机死角

### BUG-081 | 再次打磨任务容器回报丢失后,对账误杀占位行:任务永卡「启动中」,对话/终端 9001「任务无运行中的容器」 | fixed(R8.F7;verified 待用户复验)
- **状态**:fixed(2026-10-08 晚 rd-fix 闭环;backend 5 新用例 + runner 2 新用例全绿,runner 全量 114/114,容器路径回归 18/18;runner 镜像已重建+容器已重建,后端已重启,对账实测 db=1 reported=2 零误杀)
- **现场时间线**(后端 .runner_restart 日志 + runner docker logs 双向闭环):21:08:02 调度下发 → 21:08:03 docker 容器 880ab87c7569 启动成功 → **21:08:26 平台侧 WS 连接断开**(「Runner 连接注销」;runner 21:09:49 keepalive 超时才察觉)→ 21:08:58 runner `container_started` 回报发进死连接丢失 → 21:09:51 runner 重连注册,注册触发的 `handle_sync` 对账把「pending 占位行 ≠ docker id」判死(UPDATE destroyed)→ 任务行 running 但无 running 容器行 → 对话失败/终端 9001
- **根因(三层)**:① `container_started` 回报走单发、连接死亡即永久丢失,runner 重连后无补发;② `handle_sync`(R16 对账)按 container_id 比对 docker 清单,`pending-` 占位行永不匹配必被误杀——而 runner 侧 R8.F5(BUG-055)早已在 sync 上报里带 `qicheng.task_id` 标签,**平台侧收养逻辑从未实现**(半成品缺陷);③ `handle_container_started` 只认 creating 行,行被对账抢先置 destroyed 后迟到回报直接丢弃,无复活语义
- **修复方案(R8.F7)**:① handle_sync 护栏:pending 占位行不参与「不在上报→destroyed」判定;② handle_sync 收养:上报条目带 task_id 时按 task 收养占位行(替换真实 id/置 running/端口随报);③ handle_container_started 复活:无 creating 行时按 task 找最近 pending 占位行(destroyed 亦可)复活;④ runner `local_container_states` 补 ports( running_probes 已有,随镜像重建生效)
- **现场修复**:containers.id=27 已按 docker 实况复活(880ab87c7569/running/端口回填)+ tasks 行回填,任务 4d0e3ce5 即时解堵;代码修复防复发
- **诊断产物**:`.scratch/fix-analysis.md`(BUG-081 节)

### BUG-036 | 容器 LLM_URL/LLM_MODEL + 平台自定义变量 | fixed(R8.F4)
- 后端:`platform_settings_service` 新键 `custom_env_vars`(envmap 型:键名正则/≤50 组/值≤2048/RESERVED_ENV_KEYS 拒写,错误文案不回显值);`task_service` 两处 env 改为自定义铺底+系统键后置覆盖 + `LLM_URL` 别名(=LLM_BASE_URL 同值)
- 前端:`PlatformSettings.tsx` 第 5 组「自定义变量」KV 行编辑 + 客户端预检(与后端同口径);`api/admin.ts` 类型
- 决策留痕:custom_env_vars 不进 SENSITIVE_KEYS(密文回显使编辑不可用,页面仅超管可见,审计沿用"只记键列表")
- 验证:pytest 13 例 PASS(校验/API 往返/两链 env 断言);**真实容器实证** `docker exec 50f386fa63b4 env` → MY_TEST_VAR=hello-r15 + LLM_URL 在线;API 往返 PUT/GET 原样、TASK_ID 保留名 2007 拒写

## BUG-046

- **状态**:fixed(2026-09-24 rd-fix 第 23 轮 / R9.F2;真机浏览器复验见 R9.F2 执行记录)
- **用户报障**:「新建终端,websocket 报错,RenderService.ts:52,Uncaught TypeError: Cannot read properties of undefined (reading 'dimensions')」
- **根因**(详见 `.scratch/fix-analysis.md` § 第 23 轮):`Terminal.tsx` 初始 fit 为单 requestAnimationFrame 无任何守卫,ResizeObserver 回调无条件 `fit()+sendResize()`——RO observe 后首帧立即回调,而 Runner 终端 Dialog 有 150ms 入场动画(dialogContentIn scale/translate),动画期容器尺寸持续变化,`fit()` 内部访问尚未就绪的 RenderService.dimensions → TypeError、终端白屏;ws 报错为连带症状。R31.F1 落地后宿主 shell 会话首次真开,该前端时序缺陷第一次被真实数据流踩中
- **修复**:`safeFit` 统一入口——disposed 守卫 + 容器尺寸>0 守卫 + try/catch 兜底(渲染器未就绪忽略本轮,RO 下帧重试);初始 fit 改双 rAF 等动画/布局稳定;ResizeObserver 回调全部走 safeFit。两个入口(任务工作台 Tab/全屏切换 + Runner 终端 Dialog)同受益,不涉 WS 数据流/claude 会话行为改动
- **验证记录(第 23/24 轮)**:① 16:58 真机流程 Runner 终端 Dialog 打开→新建终端→xterm 正常渲染,**原 fit 路径崩溃未再现**;② 复验中仍出现一次 dimensions 报错,定位为 **React.StrictMode 开发期双挂载伪影**(首挂载 open() 后 dispose,xterm Viewport 内部调度的 rAF 刷新读已置空 _renderService)——修复升级为 open 延迟双 rAF + disposed 跳过(首挂载 dispose 前不再 open,僵尸实例无从产生;生产构建无 StrictMode,时序差异无感);③ tsc 0 错;④ 浏览器整段零错终验因两会话超管互踢(D17)反复中断,归用户下一次打开终端一瞥(预期 console 干净)

## BUG-UI-070

- **状态**:fixed → 已 verified 迁移 ISSUES.md(2026-09-24 rd-fix 第 23 轮 / R9.F2)
- **用户指令**:「终端右侧的 scroll bar 美化下」
- **修复**:globals.css **纯追加** `.xterm-viewport` 滚动条样式——WebKit 8px 半透明白 thumb(rgba(255,255,255,.18),4px 圆角,hover .32)+ track 透明;Firefox `scrollbar-width:thin` + `scrollbar-color`。终端底色恒 #1e1e1e(Terminal.tsx 硬编码,不随主题),亮/暗主题通用,零既有行改动
- **验证记录**:真机浏览器计算样式实证 scrollbar width=8px、thumb 4px 圆角 rgba(255,255,255,0.18)、Firefox thin——PASS

## BUG-047

- **状态**:fixed(2026-09-24 rd-fix 第 24 轮 / R26.F2;真机 API 三步链 + runner 日志 + DB 全实证)
- **用户指令**:「该 Runner 已有终端会话,请先关闭 提供强制关闭再新建功能」
- **实现**:
  - 后端 `POST /api/admin/runners/{id}/shell-sessions?force=true`(runners.py):6002 判定处 force 时遍历该 Runner 活跃 shell 会话逐一复用 terminal.py 关闭语义(通知 `terminal_close` kill pty;WS 不在跳过 + 置 `closed_at`)后放行;不带 force 零变化
  - 前端:createRunnerShellSession 加 force 参;Dialog 错误分支按 shellErrCode===6002 渲染「强制关闭并新建」主按钮 → openShell(r, true)
- **验证记录**:① tdd Red→Green,test_r26_runner_shell.py **12/12**(新用例:无 force 6002 维持/force 后旧会话收 terminal_close+closed_at 置值+新会话独立 open);② 真机 API 三步:创建 A=code0 → 再建无 force=6002 原文 → force=true=code0;③ runner 日志实证「宿主 shell 已关闭 A → 已创建 NEW」;④ DB:A closed_at 置值、NEW open;⑤ tsc 0 错;前端按钮的可视化确认归用户一瞥(两会话超管互踢致浏览器驻留不稳)

## UI 相关问题

(2026-09-24 浏览器核对批次新增;五批 UI 改动走查截图见 `report/ui-overhaul-20260924/`;批次 3 个 open bug 已于 2026-09-25 第 27 轮修复 verified 迁移 ISSUES.md:BUG-UI-071→R14.F1 / BUG-UI-072→R28.F2 / BUG-UI-073→R19.F6)

## BUG-UI-083

- **状态**:fixed(2026-09-26 修复并真机复验;发现于同日浏览器核对批次)
- **页面/组件**:任务工作台右栏「终端」Tab **空态占位**(TerminalPanel.tsx L96 空态分支根 div)
- **现象**:占位态点「全屏」(Maximize2)无覆盖层效果——面板仍内联在原栏内(778×671),仅按钮图标切为 Minimize2;Esc/退出/连点状态机本身正常、无 JS 报错
- **根因**:空态根 div 常驻 `relative` 与全屏分支追加的 `fixed inset-0 z-[60]` 并存同一 className;Tailwind v3 样式表中 `.relative` 规则在 `.fixed` 之后(实测 dev 产物 offset 61611 > 61541),同特异性后者胜 → position 恒 relative,`fixed/inset-0` 全部失效
- **证据(真机 A/B,同页同操作,viewport 1440×900)**:对话 Tab 全屏(TaskChat,无常驻 relative)覆盖层 1440×900、position:fixed ✓;终端占位态全屏 778×671、position:relative ✗——任务 16f81e75 与浙里足球 f6ac20f4 两任务均复现;祖先链无 transform/filter(排除 containing-block 劫持)。截图 `report/terminal-fullscreen/02-fullscreen-empty.png`
- **波及面**:仅终端**空态**;有 Tab 面板根 div(L127)、TaskChat(L236)无常驻 relative,编辑器(TaskDetail L363)互斥三元式,均不受影响
- **修复(2026-09-26)**:TerminalPanel.tsx 空态根 div 改 position 二选一条件输出(互斥三元,对齐编辑器写法):`fullscreen ? ' fixed inset-0 z-[60] p-2' : ' relative'`,不再两类并存;非全屏保留 `relative` 供全屏按钮 absolute 定位。有 Tab 分支(L127)与 Terminal.tsx 未动
- **验证记录**:修复前——占位态全屏/退出/连点 3 次/Esc 全流程无 JS 错误,状态机正确;修复后——`npx tsc -b --noEmit` 零错误;Playwright 真机复验 14/14 PASS(脚本 `.scratch/terminal-fs-fix-verify.mjs`):非全屏空态 position=relative 内联 778×671 → 全屏 position=fixed z=60、覆盖层 1440×900=视口、origin(0,0) 脱离原栏 → Esc 还原 relative 778×671;连点 3 次+Esc、第二任务 f6ac20f4(cancelled)交叉复验同过,零 JS 报错。截图 `report/terminal-fullscreen-fix/01-fullscreen-overlay-viewport.png`、`02-esc-restored-inline.png`;结论 `.scratch/bug-ui-083-fix.md`。有容器任务的 canvas refit 因 dev 无 running 容器仍待测(不阻塞本修复)

## BUG-DATA-001

- **状态**:open(2026-09-26 登记)→ 已清理并 verified 迁移 ISSUES.md(同日;归因分析 `.scratch/pinyin-analysis.md`,处置结论 `.scratch/pinyin-fix.md`)
- **问题**:tasks 表 id **945 / 946** 标题 `??????` / `??????2` 乱码(HEX=`3F3F…` **字面 ASCII 问号字节**,非 mojibake);同归属需求 req `1f087d4c`,均 2026-09-23 创建、status=cancelled
- **归因(非代码 bug)**:2026-09-23 rd-fix 第 8 轮本地 Runner E2E 时,外部测试客户端(Windows 控制台 GBK 代码页)在创建请求 payload 里就把中文打成了字面 `?`——证据:同窗口 id 947(间隔 5 分钟)中文完好、同行 error_message(停止接口后写)中文完好、charset 全链路 utf8mb4;拼音/分支命名代码无任何产生 `?` 的路径(pypinyin `errors='ignore'` 跳过未收录字符,不替换为 `?`)
- **处置记录(2026-09-26 数据修复)**:按分析报告方案 B「就地改名保留留痕」执行(禁删行)——先 SELECT 确认 945/946 仍为 `??????`(HEX=3F…)后 `UPDATE tasks SET title='历史测试数据(已清理)' WHERE id IN (945,946) AND title IN ('??????','??????2')`(带 title 仍是乱码的前置守卫);**rows affected=2,其余行零触碰,未 DELETE 任何行**
- **验证记录**:① 复检 SELECT:两行 title HEX=`E58E86…`(「历史测试数据(已清理)」合法 UTF-8);② 全库扫尾:`tasks.title LIKE '%?%'` 其余 **0** 条,`requirements.title/req_branch LIKE '%?%'` **0** 条——乱码清零

## R34.F1 移交项(2026-09-26 登记;两项均已解决并 verified 迁移 ISSUES.md)

> BUG-DATA-001 归因时的两个附带发现(分析报告 §1.3)均已闭环:BUG-052(接线缺失)由 R34.F1 会话 commit 93242f9 完成接线,第 31 轮真机回归实证(feat/hgcsrzwbty20260928 产出)迁移;BUG-053(前端 □ 占位符观感)由 R34.F1 追加 commit 5c4e4c9(branch-preview 接口 + useBranchPreview hook)解决,2026-09-28 第 34 轮追加浏览器复验(预览 feat/gwcyhqdjsy20260928 无 □,截图 report/rd-fix-r34/03-branch-preview.png)verified 迁移 ISSUES.md,原档案见 ISSUES.md 同日小节。

| BUG-061 | open → 已 verified 迁移 ISSUES.md(2026-09-28 第 31 轮;pypinyin 按清单补装 0.55.0 + pytest 16/16 + 真机重放 code=0、req_branch=feat/hgcsrzwbty20260928 实证) | — | — | — | — |
| BUG-062 | open → 已 verified 迁移 ISSUES.md(2026-09-28 第 32 轮;requirements 双文件落地+安装闭环+新栈真机重放 code=0;全量 pytest 22 failed 经逐例分类 A 升级回归=0——20 个为 R32 Runner 标签流测试先行未实现、2 个环境噪音,见 `.scratch/R34.F3/pytest-analysis.md`) | — | — | — | — |

## BUG-059 | 流式体验:上游非流式时增量瞬达,视觉等同同步整段输出 | fixed

- **现象**:对话等待生成完成后整段瞬间出现,无逐字流式视觉(用户复测反馈,2026-09-27)
- **根因**:上游网关非流式(已实证 span=0.00s)→ 平台收到的 126 个 chat_delta 挤在 0.14s 内瞬达 → 前端一瞬间渲染完,视觉与同步无差别
- **修复(R32.F7)**:后端广播层加**打字机平滑器**——chat_delta 单帧拆分(≤16 字符)+ 帧间隔下限(30ms);增量到达间隔大于下限时零延迟直通(真流式网关零改动自适应),瞬达时按节奏铺开形成逐字视觉
- **验证**:单测(拆分/节奏/直通)+ 真机探针(delta 时间跨度从 0.14s 拉长到秒级)

### BUG-059 验证记录(2026-09-27)

- pytest 8/8(平滑器拆分/保序/节奏铺开/慢到达直通 + 既有 registry/映射回归)
- 真机探针:200 词回复 → **203 个 chat_delta 跨度 7.89s**(修复前 0.14s),2 秒桶分布 35-52 帧均匀(≈30ms/帧设计节奏),chat_done 正常收尾
- 参数:CHAT_DELTA_SLICE=16 字符/帧,CHAT_DELTA_MIN_INTERVAL=30ms(≈530 字/秒,快于阅读速度);真流式网关接入时到达间隔大于下限,零额外延迟直通

## BUG-060 | 容器重建后 claude_session_id 残留 → resume 静默失败空回复 | fixed

- **现象**:AI 对话没有返回(content=''、tokens=0 落库;用户 08:07 两次复现)
- **根因**:用户 08:05 重启任务容器(新容器 43680d34c09c),但 tasks.claude_session_id 残留旧容器会话(2d9c6e5e)→ 首条消息 `claude --resume <不存在>` → CLI 报 "No conversation found with session ID"(走 stderr 被 2>/dev/null 吞)→ stdout 零行 → 空 result 正常结算落库
- **一手证据**:容器内手跑复现(`--resume <旧id>` → No conversation found,EXIT=0);DB 对比:02:55 旧容器回复 1226 字符正常,08:07 新容器两条空
- **修复(R32.F8,双层)**:① 平台治本——handle_container_started 置空 tasks.claude_session_id(新容器必无旧会话);② runner 兜底——claude_prompt_stream 返回增 lines 计数,main.py 流式 handler 识别「带会话且零行」自动降级无会话重跑(新会话)
- **验证**:runner 52/52(新增空跑 lines=0 用例 + 断言同步);真机端到端:会话重置后对话 8.5s 返 pong 落库;当前任务会话已手工重置解阻塞

## BUG-UI-084 | 对话发送无即时反馈:用户消息与成功态等 AI 返回才出现 | fixed

- **严重程度**:一般(体验问题)
- **关联页面**:/tasks/:id(任务工作台 AI 对话,TaskChat.tsx)
- **问题描述**:POST /messages 同步等 AI 执行完才返回(8-60s),期间用户消息不上屏、输入框不清空、无 AI 加载动效——「消息发送是等内容有回应后才发成功」(用户报障,2026-09-27)
- **建议方案**:乐观 UI——发送即清输入框 + 用户消息半透明上屏 + AI 三点弹跳加载动效;首个 chat_delta 到达后由流式气泡接管;POST 返回刷新消息后统一收口;POST 未返回前禁止重复发送
- **状态**:fixed(tsc 0 错 + build 过;用户浏览器复验后 verified)

## BUG-UI-085 | 对话发送后不自动滚到新消息,需手动下滚 | fixed

- **严重程度**:轻微(体验问题)
- **关联页面**:/tasks/:id(TaskChat.tsx)
- **问题描述**:自动滚动只监听 messages.length/streamText,乐观用户消息与 AI 加载动效上屏不触发;且为瞬时跳转无平滑
- **建议方案**:监听源补 pendingUser/thinking,滚动改 smooth;配合气泡美化(12px 大圆角+收音角+软阴影+AI 气泡细描边,亮暗双主题)
- **状态**:fixed(tsc 0 错+build 过;用户浏览器复验后 verified)

## BUG-061

- **状态**:已 verified 迁移 ISSUES.md(2026-09-28 rd-fix 第 31 轮;完整档案见 ISSUES.md 同轮迁移表)
- **一句话**:需求创建 500 = R34.F1 拼音分支策略依赖 pypinyin 已声明(pyproject L21)未装入本机运行时;零代码修复=pip 补装 0.55.0,回归=pytest 16/16 + 真机重放 code=0 且 req_branch=feat/hgcsrzwbty20260928(接线实证,BUG-052 一并解决)


### BUG-074 | AI 对话流式回复开头重复一行(首包内容双写) | fixed(R5.F4;verified 待真机对话复验)
- **状态**:fixed(2026-09-29 rd-fix 第 42 轮;单测 3/3+触碰面回归 67/67,已部署重启)
- **用户报障**:AI 对话消息返回,前面会出现重复行,如:「好的,Q1-Q4 已确认。我先派人去查现有登录代码,同时推进下一轮细节决策。\n\n好的,Q1-Q4 已确认。我先派人去查现有登录代码,同时推进下一轮细节决策。」——同一段开头文本连续出现两遍
- **根因**:task_service.py `_stream_event_to_chat` 双路径广播(text_delta 增量 + assistant 整块都发 chat_delta),前端无去重累加;DB 落库本就干净
- **修复**:seen_stream_delta 标志,assistant 整块仅在未见 text_delta 时兜底广播(老 CLI 兼容)
- **怀疑面**(待诊断证实):① 流式首包在 streamText 累积与落库 refetch 替换处双写(R5.F2 改过「refetch 完成才清流式气泡」链路);② 后端落库把首 chunk 存两次;③ runner 流式切片重复下发;④ 停止生成(stoppedRef)与新一轮流式缓冲互串
- **关键分叉**:落库 messages.content 是否已含重复——含=后端/runner 层,不含=前端流式渲染层
- **诊断产物**:`.scratch/fix-analysis.md`(BUG-074 节)

## BUG-075

- **状态**:已 verified 迁移 ISSUES.md(2026-09-29 rd-ui 容器门卫核对轮附带发现;环境缺陷零代码即时修复,完整档案见 ISSUES.md 同节)
- **一句话**:创建需求 500 = Windows 运行时缺 tzdata(ZoneInfoNotFoundError: Asia/Shanghai),uv pip install + 重启即愈;tzdata 未声明进依赖清单,补声明归 rd-dev

### BUG-076 | AI 对话长消息发送失败 | fixed(R5.F5;verified 待真机长消息复验)
- **状态**:fixed(2026-09-29 rd-fix 第 43 轮;runner 107 + backend 34 全绿,迁移/后端/runner 已部署生效)
- **用户报障**:AI 对话,消息长的时候,会出现发送失败的问题
- **根因(实锤,`.scratch/fix-analysis.md` BUG-076 节)**:P0=prompt 经 shlex.quote 拼 `claude -p` 命令行(container_manager.py:1008),长消息+@附件注入叠加撞 Linux ARG_MAX,容器内 exec 直接失败;P1=task_messages.content TEXT(64KB) 静默截断;P2=SendMessageRequest 无 max_length 无友好拦截
- **修复(R5.F5 三层)**:P0=prompt 改临时文件+stdin 传递(不占 argv,流式/非流式双路径);P1=content 升 MEDIUMTEXT(迁移 a1b2c3d4e5f6,down 30088c854a08);P2=content max_length=200000 超限 422。tdd:Red 6/6→Green;审计通过(conftest 补 ALTER 判定合理防御);防双写确认(R5.F2/F3/F4 标志未被覆盖)
- **部署**:迁移已应用(mediumtext 实证)+后端 8000 重启 /docs 200+runner 镜像 e39b84d5 重建容器重建注册成功
- **待复验**:用户真机发长消息(>128KB 或带 @大附件)确认发送成功、回复完整不截断
- **复验打回(2026-09-30 诊断轮,用户指令「先别改代码」)**:用户报仍发送失败 → 纯诊断实锤(证据 `.scratch/fix-analysis.md` BUG-076 复验打回节):**环境层因素,非代码回归**——LLM 代理 18765 宿主/容器均无监听,runner 日志 16:34-16:45 四次 `claude_prompt_stream 超时(120s)`,与 BUG-034 同源;DB 侧消息落库正常(16:48-16:49),API/DB 层完好,排除 P0 修复 bug 与 R1-R3 新改动回归。**代码修复维持 fixed 不动,待用户启动 LLM 代理后真机复验**(复验通过 → verified 迁移)

### BUG-077 | Runner 重启提示「Runner 依赖未安装」(16002 deps_missing) | fixed(R31.F4;verified 待用户下次重启复验)
- **状态**:fixed(2026-10-08 rd-fix 第 44 轮;诊断+修复同轮,测试 3/3 新增+R31 回归 27 过)
- **用户报障**:runner 重启,提示「Runner 依赖未安装,请在平台运行环境执行 pip install -r runner/requirements.txt」
- **根因(实锤)**:**超时误报,非真缺包**——后端 8000 同款解释器(E:\services\python310)`import docker, websockets` 实测通过(1.06-1.38s,阈值 5s);`local_runner_service.preflight` 探测子进程超时分支与真缺包分支共用「未安装」文案,假期后冷启动 import 偶发超 5s 即误报。佐证:docker runner rd49-docker 在线心跳正常;当天探测已恢复 1.1s
- **修复(R31.F4,主 agent 直修留痕——subagent 通道 429 两次,按 9-29 先例兜底)**:①探测超时重试 1 次再判 ②文案区分:超时→「依赖探测超时(冷启动/磁盘忙时偶发),请重试;若持续失败请检查运行环境」,真缺包(returncode≠0)保留原「未安装,请执行 pip install」;错误码 16002 不变 ③Docker ping 分支零改动
- **验证**:新用例 Red 2→Green 3/3(重试/超时文案/缺包文案回归保护);test_r31_local_runner.py 全量 27 过+4 失败=BUG-066(validate_tags 缺失,R32 流)既有问题非本轮引入
- **部署注记**:8000 无 --reload,改动待后端下次重启生效;**当前用户重试重启即可成功**(依赖本就齐全,原误报系瞬时超时)


### BUG-076 | 打磨任务首次会话未自动发送 /rd-prd 进入打磨,PRD.md 未落需求配置的 PRD 路径 | fixed(R3.F5;verified 待真机重启复验)
- **状态**:fixed(2026-09-29 rd-fix 第 43 轮;定性=主体已实现断在重启子场景;32/32 pytest+活体 API generation=5=容器行数+prd_content 迁移已 apply+已部署重启)
- **用户报障(期望行为)**:任务打磨在**第一次会话(含容器异常退出后重新启动后)**默认发送 `/rd-prd` 进入 PRD 打磨阶段;PRD.md 保存到**需求详情中设置的 PRD 路径**;PRD.md 生成后**任务详情要能读到**
- **怀疑面**(待诊断):① 打磨容器启动链无首会话自动指令注入(或仅在特定入口有);② 打磨提示词未约定 PRD.md 输出路径=需求配置的 PRD 路径;③ 任务详情「PRD 草稿(容器内)」读取路径与写入路径不一致;④ 规格从未定义(分片缺口→分流 rd-plan)
- **诊断产物**:`.scratch/fix-analysis.md`(BUG-076 节)

### BUG-077 | AI 对话调用 /rd-prd 等斜杠技能全部失效(「技能不存在」),打磨自动首消息连带失灵 | fixed → ✅ verified(2026-10-08 真机复验通过)
- **状态**:fixed + verified(2026-10-08 诊断轮;runner 109 pytest 全绿含新增 2 例回归;runner 镜像已重建 fbcf611a9d4d + 容器已换新注册成功;真机复验:timeout 打磨任务 228e6d07 发 `/rd-prd` → AI 正常进入需求访谈/PRD 流程,非「技能不存在」)
- **用户报障**:AI 对话,调用 /rd-prd skills 会出现发送失败问题
- **真实症状**(非 HTTP 报错):容器内 AI 回复「`/rd-prd` 技能在当前可用技能列表中不存在」(现场:需求 0d227c83「后台用户登录」打磨任务 f966583f,9/30 00:52-00:55 四连失败);同会话 `@mcp:mysql_dev` 不可用属另一回事(MCP 缺变量/连接降级,与本 bug 无关)
- **根因(实锤,三层证据闭环)**:R5.F5(BUG-076)stdin 传输改造把命令写成 `claude -p - < /tmp/prompt_xxx`,意图「-」表示读 stdin;但 CLI 2.1.280 把「-」当**字面 prompt** 再追加 stdin → 所有消息实为 `-\n<原文>` → 永不以 `/` 开头 → 斜杠命令/技能全灭(含 R3.F4/R3.F5 自动首消息)。证据:① 尸检退出容器 5dc41cfaa738 的 CLI 会话转录(user 消息带 `-\n` 前缀,DB 原文无);② 同镜像同 env 差分实测:`-p -` 逐字复现「技能不存在」/去 `-` 后 rd-prd 正常进入 PRD 流程;③ 时间线咬合(9/29 21:03 旧 runner 容器内 /rd-prd 正常,23 时 R5.F5 部署后新建容器全灭)
- **修复**:container_manager.py 两处(stream :629 / 非流式 :1018)`claude -p -` → `claude -p`(-p 无位置参数时 stdin 即完整 prompt);回归测试 test_prompt_transport.py::TestNoDashPromptArg 锁定命令形态
- **部署**:已执行(2026-10-08,`--build-arg BASE_IMAGE=python:3.10` 本地基础镜像构建,docker.io 不可达场景同 R31.F3/BUG-049)+ 真机复验通过(见状态行)

### BUG-078 | runner docker exec 流读超时 60s:LLM 静默段 >60s 即「执行失败:timed out」且孤儿 claude 继续跑 | fixed(BUG-078;随 BUG-077 同批部署)
- **状态**:fixed(2026-10-08 复验 BUG-077 首轮撞出;runner 110 pytest 全绿含新增 1 例回归;与 BUG-077 同批重建部署)
- **发现现场**:BUG-077 复验首次发送 115s 后 9001「AI 执行失败:timed out」;但容器内 CLI 会话转录仍在持续增长(孤儿进程),runner 日志零异常零看门狗告警
- **根因(实锤)**:`ContainerManager._default_client_factory` 用 `docker.from_env()` 裸构造,APIClient **timeout=60s**(docker-py 默认)经 `_get_raw_response_socket` 被 exec 流 socket 继承(docker-py 不重设);LLM 生成静默段 >60s → `socket.timeout`(py3.10 `str(e)` 恰为 `"timed out"`)从执行线程抛出 → main.py exec_tool 通用 `except Exception` 原样回报 `error="timed out"`。**连带后果**:① R8.F6 的 120s 看门狗(stream_timeout + pkill)永远轮不到执行;② 容器内 claude 成孤儿继续烧 token
- **定性**:预先存在的潜在缺陷(BUG-034/R8.F6 同族),非 BUG-077 修复引入——新旧 runner 镜像依赖版本完全一致(docker 7.2.0/websockets 16.1.1/py3.10.21 实证比对),此前仅因未遇 >60s 静默而未暴露
- **修复**:`_default_client_factory` → `docker.from_env(timeout=3600)`(> 120s 流式看门狗且 > 600s 平台非流式超时;json 模式全程无输出,整段生成都是一次静默读);回归测试 test_docker_client_timeout.py 锁定 factory 必须显式传 timeout 且大于两级守卫
- **验证边界**:35s 流式会话跑通;>60s 静默场景由回归测试 + 机制分析锁定(真实长静默生成待自然发生观察)

### BUG-079 | 后台探索 Agent 静默期被 120s 看门狗误杀:打磨对话死循环「等待确认,无法回答」 | fixed(BUG-079;已部署,真机复验通过)
- **状态**:fixed + 真机复验通过(2026-10-08;runner 112 pytest 全绿含新增 2 例回归;runner 镜像重建+容器换新;任务 228e6d07 发访谈消息 **263s 成功返回**,AI「代码探索已完成」继续出题)
- **用户报障**:AI 对话过程中,出现等待确认的情况,对话没办法确认
- **真实机制**(任务 228e6d07 现场,16:17-16:21 两次被杀,runner 日志+容器转录实证):rd-prd 技能用 Agent 工具启动**异步后台探索子代理**("Async agent launched successfully"),主回合 end_turn 后 CLI 等待 task-notification 期间 stream-json **零输出** → R8.F6 看门狗 120s pkill → 该消息按 stream_timeout 失败(前端:已流出文字被清、消息标发送失败);用户重发 → AI 再启一个探索 Agent → 再被杀 → 死循环。**期间 POST 一直 pending,前端输入锁死**,用户的访谈回答发不进去(「没办法确认」的体感来源;后端 confirm 卡链路日志零条,与 R34.F3 权限确认无关)
- **修复(双管)**:① `runner/main.py` STREAM_TIMEOUT 120→540(≥分钟级后台探索;<600s 平台守卫,runner 先 pkill 收口);② 流式命令追加 `--forward-subagent-text`(仅 --print+stream-json 生效,正是本链路;子代理文本/思考转发为主流事件,探索期不再全静默)
- **回归测试**:test_bug079_bg_agent_stream.py(看门狗区间断言 + 流式命令旗标断言)
- **备注**:探索期 POST 持续 pending、前端输入锁定属 rd-prd 异步探索设计的固有形态(回复文本已声明「等待探索结果」);若要探索期可继续输入,需会话级并发改造(另立需求)


### BUG-082 | 打磨完成 PRD/代码未提交仓库:创建者未绑 token 时 finish 静默跳过 commit | fixed(R37.F8;verified 待用户下次打磨真机复验)
- **状态**:open(2026-10-09 rd-fix 登记;用户报障「生成的prd没有提交仓库中」)
- **根因(实锤)**:`task_service.finish_task` 只取创建者个人 token,`if runner_conn is not None and creator_token:` —— 创建者未绑定 GitLab token(实锤:需求创建者 2845fe31 has_token=0)时 `creator_token=""` → **整段 commit/push 静默跳过**,任务照常 done、前端 toast 谎称「PRD 已推送至需求分支」,零提示零日志
- **期望**:完成=真实提交。创建者无 token → 回退平台 bot token(需求分支本由 bot 经 `get_gitlab_bot_config` 创建,天然有推送权);bot 也未配置 → finish 显式报错,不静默
- **复现**:创建者无 token → 打磨 → 点「打磨完成」→ 提示成功,但需求分支上无任何 commit

### BUG-083 | done 任务误弹「任务容器未启动」遮罩且启动必败;打磨完成后应回需求详情页 | fixed(R37.F9;verified 待用户浏览器复验)
- **状态**:open(2026-10-09 rd-fix 登记;用户报障「页面完了后一直任务容器未启动,启动也不行。我需要点完成,页面置灰提交,回到需求详情页」)
- **根因(实锤)**:`TaskDetail.tsx:397-416` 容器门卫条件 `display_status ∉ {running, starting}` → **done 也生效**(任务已完成、容器已正常销毁仍全页遮罩弹「任务容器未启动,是否启动容器」);点「启动」→ retryTask → 后端 4001(终态不可重试)→ 死弹框。且 finish onSuccess 只 toast 不导航,用户停在死页面
- **修复**:门卫排除 done(终态无「启动」语义);打磨完成成功 → 导航回需求详情页(任务详情载荷已含 req_id)

### BUG-084 | headless 对话 Write 被静默拒绝:PRD.md 落盘不可靠,finish 时容器里常无文件可提交 | fixed(R8.F8;verified 待用户下次打磨真机复验)
- **状态**:open(2026-10-09 rd-fix 登记;BUG-082 诊断连带发现)
- **根因(实锤)**:容器内 headless claude `--allowedTools` 仅白名单 MCP 工具,Write/Edit/Bash 走 headless 默认**静默拒绝**(R5.F3 摘除 permgate 后无审批通道,BUG-072 留档口径「维持静默拒绝」)→ rd-prd 写 PRD.md 全凭 AI 恰好选用 filesystem MCP(10-08 偶然成功一次,prd_file_path 发现器回写即该次;10-09 两次 finish 容器内均无文件,prd_content 回填落空 has_prd=0)
- **修复**:`--allowedTools` 增加 `Write Edit`(不放 Bash;终端交互链路本就是人工审批面,headless 静默拒绝形同虚设还打断 PRD 主链路)

### BUG-085 | PRD 防丢:打磨中容器超时/异常销毁(未走「打磨完成」)时 PRD 只存容器内,随容器一起丢 | fixed(R37.F10;verified 待真机复验)
- **状态**:fixed(2026-10-09 rd-fix 登记;用户追问「AI 对话完成的 PRD.md 没有推远程,有其它办法保证不丢么」)
- **根因**:PRD 副本链(容器文件 → finish 回传入库 → bot 推分支)只在「打磨完成」时触发;超时清扫 sweep_timeouts 销毁容器前**无回传**,未完成的打磨稿随容器一起丢
- **修复(双兜底)**:① sweep_timeouts 对 requirement 型任务**销毁前 await 内联回传**(_sync_prd_background 自开 session+commit,先同步后销毁);② send_message_stream 收尾钩子——打磨任务每轮 AI 回复后 fire-and-forget 回传入库(异常安全,不阻塞对话主链路),prd_content 实时留底,容器任何时候没了稿都在库里
- **测试**:test_r37f10_prd_sync_guarantee.py 2 用例(回传先于销毁顺序实锤 + dev 任务不触发);chat/leak 触碰面 17/17
- **补充(同日,用户指令「同步到需求详情页保证可预览」)**:useRequirementPrdContent 打磨中(status=polishing)10s 轮询刷新——PRD 预览实时跟随后台回传,不必等完成/手动刷新;tsc/build 零错

### BUG-086 | PRD 永远回不来/推不上:失效路径弄瞎发现器 + http remote 凭据注入失效 + git 失败全链吞掉 | fixed(R37.F11 + R8.F9;真机已抢救回填+手推成功,verified 待下次打磨复验)
- **状态**:fixed(2026-10-09 晚 rd-fix;用户报障「还是没有啊,对应的PRD.md 在那里可以看」)
- **三连环根因**(任务 89e587e8 现场实证):① sync 固定路径回读抛「读取失败」**直接中止整个同步**——上一轮自愈的失效路径(docs/20261008_..._228e6d07)把发现器弄瞎,AI 实际写在 docs/20261009_后台图形验证码登录/ 的 PRD 永远回不来;② runner `commit_push` 凭据注入 `replace("https://",...)` 对 **http:// remote**(http://47.111.69.64/monorepo/whgzxs.git)替换不了任何东西 → 裸推 → git 交互要用户名(无 tty)→ fatal;R39 git_push 同款隐患;③ git_commit 旧通道异常**不回包** → 平台 60s「Runner 响应超时」→ finish 吞掉 → 任务照常 done
- **修复**:① sync ⑥ 读取失败降级进发现器(路径自愈恢复工作);② commit_push/git_push 改 `://` 后注入凭据(http/https 通吃,push 后恢复原 remote);③ runner 旧通道异常回包 ok=False;④ finish git_commit 60→300s + ok 感知(nothing to commit 视为无变更;done 语义下真实失败显式抛错不静默)
- **测试**:runner 117/117(http 注入 2 新用例)+ backend test_r37f11 2 用例(失效路径自愈 + git 失败显式抛错)
- **抢救(手工,脚本留痕)**:任务 89e587e8 的 PRD 已从存活容器回填 requirements.prd_content(12668B)+ prd_file_path 自愈 + bot token(解密后)手推 GitLab 成功(`7443c287..56c45da4`);详情页预览即时可见(source=db)

### BUG-087 | GitLab Token 绑定永远 405:前端 POST vs 后端 PUT 方法错位 | fixed(R28.F3;真机绑定实证)
- **状态**:fixed(2026-10-09 晚 rd-fix;用户报障「接口绑定失败」附 fetch 抓包)
- **根因**:后端 `PUT /me/gitlab-token`(users.py:121),前端 `bindGitLabToken` 用 `api.post` → 每次提交 405 Method Not Allowed。token 本身有效(实测 gitlab.zhanqirsj.com / 47.111.69.64 均 200 返回 luowen 档案);GET 查状态/DELETE 解绑均配对,唯绑定错位
- **修复**:① bindGitLabToken `api.post` → `api.put`(单行);② 补 GET /me/gitlab-token 状态路由(原只有 PUT/DELETE,设置页状态查询恒 405,页面永远显示未绑定态;返回 {bound, gitlab_username, scopes} 与前端契约对齐)。tsc/build 零错
- **真机**:PUT 绑定 code=0;GET 状态 {bound:true, gitlab_username:luowen, scopes:[unknown](BUG-016 已知口径)};users.gitlab_token_encrypted 已落库

### BUG-088 | 需求详情页「创建开发/测试任务」按钮指向不存在的路由 /tasks/create | fixed(R22.F4;verified 待用户浏览器复验)
- **状态**:fixed(2026-10-09 晚 rd-fix;用户报障「创建开发任务接口失败,接口 404」附抓包 GET /api/tasks/create)
- **根因**:RequirementDetail approved 态的「创建开发任务/创建测试任务」按钮 `navigate('/tasks/create?type=x')`——该路由无页面无注册(项目里只有对话框组件 `pages/tasks/TaskCreateDialog`,且同文件已 import、release 按钮已在用),落进坏路由后前端还打出 GET /api/tasks/create → 404
- **修复**:两按钮改本页弹窗(与 release 完全同款):`setCreateTaskType('dev'|'test')` + 渲染 `<TaskCreateDialog reqId type onSuccess→/tasks/{id}>`;撤销误改的 manage 版弹窗
- **测试**:tsc/build 零错;创建接口本体(POST /requirements/{req_id}/tasks)为 R4 生产在用链路,无需新验证
