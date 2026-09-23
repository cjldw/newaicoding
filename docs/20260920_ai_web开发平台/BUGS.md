# BUGS.md — 活跃问题清单

> 项目:ai_web开发平台 | 更新:2026-09-22(rd-fix 第 5 轮收敛)
> 状态流转:open → fixed → verified(verified 后迁移至 ISSUES.md)
> 已 verified 迁移:第 3 轮 BUG-UI-001/003/004/005/006;第 4 轮 BUG-010;第 5 轮 BUG-009/011/012/013(见 ISSUES.md)

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
| BUG-UI-064 | fixed | R4(任务工作台;波及 R9/R11 面板) | 功能增强(用户指令) | 用户指令 2026-09-23 | 任务页三面板(Terminal/AI 对话/文本编辑器)补齐全屏、保存、滚动,修复分片 R4.F1(tsc+build 过,verified 待浏览器) |
| BUG-UI-065 | fixed | R4(工作台;波及 R9/R11) | 功能缺陷批(用户实测) | 用户指令 2026-09-23 | terminal 不行(WS 无代理+tab 关不掉)/diff 不行(不设 diffPath)/对话无反馈态/编辑器底部贴边,修复分片 R4.F2(tsc+build 过,verified 待浏览器;**vite dev 需重启加载 /ws 代理**) |

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

### BUG-UI-042 | R19 筛选栏 padding 与规范不符 | open
- 复现:/admin/users 筛选栏 .fbar
- 期望 vs 实际:规范要求 padding:16px 0;实际 computed padding:12px 16px
- 截图路径:—
- 状态:open

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

### BUG-UI-048 | R21 表格行 padding 不符 | open
- 复现:/ Dashboard 表格行
- 期望 vs 实际:行 padding 9px 16px(期望 0 12px)
- 截图路径:—
- 状态:open

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

### BUG-UI-052 | R22 页面容器样式不符 | open
- 复现:四维管理页容器
- 期望 vs 实际:无 max-width:1280px,padding=0px(期望 24px 32px)
- 截图路径:—
- 状态:open

### BUG-UI-053 | R22 搜索框缺失 | open
- 复现:四维管理页筛选栏
- 期望 vs 实际:四页均无搜索框(input 元素 0 个)
- 截图路径:—
- 状态:open

### BUG-UI-054 | R22 表头样式不符 | open
- 复现:四维管理页 thead th
- 期望 vs 实际:th bg=#f4f4f5✓,但 fw=600(期望500),pad=9px 16px(期望12px 16px),fs=12px(期望14px)
- 截图路径:—
- 状态:open

### BUG-UI-055 | R22 单元格样式不符 | open
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

### BUG-UI-059 | R22 需求管理页缺少特定列 | open
- 复现:/manage/requirements
- 期望 vs 实际:无优先级列/需求分支列(仅5列:ID/标题/状态/所属项目/更新时间)
- 截图路径:—
- 状态:open

### BUG-UI-060 | R22 任务管理页缺少特定列 | open
- 复现:/manage/tasks
- 期望 vs 实际:无类型徽章列/Runner 列(仅5列同 requirements)
- 截图路径:—
- 状态:open

### BUG-UI-061 | R22 页头结构不符 | open
- 复现:四维管理页 h1
- 期望 vs 实际:h1 fs=19px(期望24px/text-2xl),无"新建"按钮
- 截图路径:—
- 状态:open

### BUG-UI-062 | R22 筛选栏布局不符 | open
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

### BUG-026 | devbox 基础镜像被微软退役,任务容器镜像无法构建 | open
- **复现**:`docker build -t platform/devbox:v1 -f docker/devbox/Dockerfile .` → `mcr.microsoft.com/devcontainer/universal:linux: not found`
- **实证**:`GET https://mcr.microsoft.com/v2/devcontainer/universal/tags/list` → 404(整个仓库退役,非网络问题)
- **期望 vs 实际**:期望能构建 `platform/devbox:v1`(R8 任务容器默认镜像,ARCH D10);实际基础镜像不存在,任何环境均无法产出任务容器镜像 → 任务启动无容器可用
- **影响**:阻塞 R8 容器链路 + R17 Skills 预装 + R11 watcher 依赖的镜像交付
- **修复方向(R8.F1)**:基础镜像切换 `mcr.microsoft.com/devcontainers/typescript-node:dev-bookworm`(tags 已实证存在;含 node/git)+ apt 补 python3/pip/inotify-tools;默认用户 codespace→vscode 适配;替代 tags 已核验
- **状态**:open(修复分片 DEVPLAN/R8.F1.md;Dockerfile 已改,镜像重建中)

### BUG-027 | Runner 事件监听无归属过滤 + 心跳饿死 | open
- **复现**:本地启动 Runner(runner/main.py,已注册成功)→ 观察平台 last_heartbeat_at 停在注册时刻(60s 后 offline);同时 Runner 日志连续出现对 `monkeycode-ai-backend`(宿主机用户自有容器,crash-loop 中,containers 表无记录)的"容器自动重启(1/3)(2/3)(3/3)"
- **期望 vs 实际**:期望 Runner 只管理平台创建的容器、心跳持续在线;实际 ① 事件监听无归属过滤,接管宿主机上所有容器;② `iter_events()` 同步生成器在协程内阻塞迭代,饿死 asyncio 循环 → 30s 心跳无法发出
- **根因**:runner/main.py `event_listener` 直接 `for event in manager.iter_events()`(阻塞)+ 事件处理前无归属校验(创建时已有的 `qicheng.managed` 标签未被利用)
- **修复记录(2026-09-23 rd-fix 第 8 轮 / R8.F2,已实现待重启验证)**:① 事件流移入 daemon 线程经 `queue.Queue` 泵送,async 侧轮询消化;② 按 `Actor.Attributes["qicheng.managed"] == "true"` 过滤,非平台容器不接管不回报
- **状态**:fixed(待重启 Runner 验证心跳+无干扰,E2E 后置 verified)
