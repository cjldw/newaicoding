# 开发计划:Skills 市场安装 + 系统级已安装列表(合并)

> PRD:./PRD.md(市场安装,已确认)+ ../20260927_系统级skills与mcp列表/PRD.md(系统级列表,已确认)
> 创建日期:2026-09-26
> 状态:**已确认**(人工核对通过)

## 需求概述

Skills/MCP 能力域两 PRD 合并:**市场安装**(内置 ModelScope+skills.sh 双源,后端代理搜索,一键安装 SKILL.md 到项目,参照 find-skills)+ **系统级已安装列表**(临时容器探测镜像内置 skills/MCP 入库,只读展示,合并进 AI 对话 /skills、/mcp 候选)。

**PRD 映射**:DEVPLAN R1-R4 = 市场安装 PRD 的 R1-R4;DEVPLAN R5-R7 = 系统级列表 PRD 的 R1-R3。

## 技术约定

- **UI 一律沿用现有风格**(用户强调):globals.css 类体系 + 自研 ui 组件(zinc token),Dialog/Table/Tab/徽章零新视觉;新 hooks 照 react-query 体系
- 后端:httpx 适配器照 gitlab_service 风格(_get_client/timeout/try-finally);白名单 platform_settings_service SETTING_KEYS+validate json 分支;审计 audit_write
- 容器探测:runner 新增 `probe_claude` 指令(start 空仓库容器→exec_capture `ls /root/.claude/skills/`+`cat /root/.claude.json`→stop,单次调用完成,免 pending 登记;照 claude_inject 先例 runner/main.py:429)
- 迁移:skills 加 source/source_url 列(不动 scope ENUM);新表 claude_system_assets;notifications 无涉
- ⚠️ AI 对话 /mcp 候选**不存在现成实现**(R32 只做了 /skills)——R7 需新做 /mcp 补全 UI(照 /skills 的 TaskChat :152-182 模式)

## 当前进度

**当前进度: 1/7 - R2 开发中**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 市场源配置(超管) | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R1.md |
| R2 | 市场搜索接口(后端代理) | M1 后端 | ⬜ | ./DEVPLAN/R2.md |
| R3 | 一键安装到项目 | M1 后端 | ⬜ | ./DEVPLAN/R3.md |
| R4 | 市场搜索安装 Dialog | M2 前端 | ⬜ | ./DEVPLAN/R4.md |
| R5 | 系统级采集(probe_claude) | M1 后端+Runner | ⬜ | ./DEVPLAN/R5.md |
| R6 | 系统级只读展示 | M1 后端+M2 前端 | ⬜ | ./DEVPLAN/R6.md |
| R7 | 对话 /skills /mcp 候选合并 | M1 后端+M2 前端 | ⬜ | ./DEVPLAN/R7.md |

## 模块拆分与时间线

| 模块 | 包含需求点 | 依赖 | 预计耗时 | 顺序 |
|---|---|---|---|---|
| M1 市场链路 | R1→R2→R3→R4 | - | 1.5d | 1 |
| M2 系统级链路 | R5→R6→R7 | 容器基建 | 1.5d | 2 |

## 业务旅程(跨需求点)

| 旅程 | 链路 | 关键数据传导 |
|---|---|---|
| J1 市场 skill 装进容器 | R2 搜索 → R3 入库 → (任务容器启动)注入 | 安装即进 list_project_skill_contents |
| J2 内置能力可见 | R5 探测入库 → R6 展示 → R7 对话候选合并 | 系统级只读,不参与注入配置 |

## 范围外

- 多文件 skill 完整安装、版本锁定/update、自定义索引格式市场、任务启动自动回采、系统级启停管理、MCP 模板硬编码改造(mcp_service.py:29 与本次无关)

## 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-09-26 | 初始版本(两 PRD 合并;/mcp 需新做补全 UI 按调研修正范围) | rd-plan 调研 |
| 2026-09-27 | R1 完成+枚举笔误 modescope→modelscope 修正+P2 hook 解包修复 | rd-dev R1 收口 |
