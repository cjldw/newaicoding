# BUGS.md — 活跃问题清单

> 项目:ai_web开发平台 | 更新:2026-09-22(rd-fix 第 5 轮收敛)
> 状态流转:open → fixed → verified(verified 后迁移至 ISSUES.md)
> 已 verified 迁移:第 3 轮 BUG-UI-001/003/004/005/006;第 4 轮 BUG-010;第 5 轮 BUG-009/011/012/013(见 ISSUES.md)

| BUG | 状态 | 关联需求点 | 类型 | 来源 | 摘要 |
|---|---|---|---|---|---|
| BUG-007 | fixed | R16(波及 R9/R11 产物) | 部署阻塞 | rd-ship 发布检查 | docker/runner/Dockerfile 缺 terminal_manager.py / file_watcher.py,Runner 镜像启动即 ImportError |
| BUG-UI-002 | 已核实:与稿一致,不修 | admin-audit-logs | UI 偏差 | Playwright 核对 2026-09-22 | 核对时审计表为空,`totalPages>1` 不成立 → 分页整体不渲染;代码中 `.card-foot` 包裹存在(AuditLogsPage.tsx:257),与 vp"审计页无分页脚注"一致 |

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
