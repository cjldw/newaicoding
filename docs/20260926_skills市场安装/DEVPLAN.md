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

**当前进度: 7/7 (100%) - 全部完成(待 rd-check 全量校验)**

| 需求点 | 名称 | 模块 | 状态 | 详情文件 |
|---|---|---|---|---|
| R1 | 市场源配置(超管) | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R1.md |
| R2 | 市场搜索接口(后端代理) | M1 后端 | ✅ | ./DEVPLAN/R2.md |
| R3 | 一键安装到项目 | M1 后端 | ✅ | ./DEVPLAN/R3.md |
| R4 | 市场搜索安装 Dialog | M2 前端 | ✅ | ./DEVPLAN/R4.md |
| R5 | 系统级采集(probe_claude) | M1 后端+Runner | ✅ | ./DEVPLAN/R5.md |
| R6 | 系统级只读展示 | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R6.md |
| R7 | 对话 /skills /mcp 候选合并 | M1 后端+M2 前端 | ✅ | ./DEVPLAN/R7.md |

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
| 2026-09-27 | R2 完成:市场搜索接口(后端代理双源,400/502 分界+5min 缓存);QA+源配置回归 48/48 全绿(含收口修复 6 新用例) | rd-dev R2 收口 |
| 2026-09-27 | R2 契约裁定:响应 items[].market 与请求参数统一回显 **type 值**(modelscope/skillssh),非 PRD 字面「源名」(skills.sh)——请求/响应同值自洽,R3 安装 round-trip {market,ref} 依赖同值;QA 测试矩阵扩至 25 用例全绿 | rd-dev R2 QA 甄别 |
| 2026-09-27 | **多会话协同裁定**:R3 由并发会话认领(其进度行已声明「协同确认」,工作区已有其半成品:迁移 b8e4d2f6a9c1/test_skill_install_remote 等);本会话已停止 R3 subagent(盘点期,未落盘冲突),**错位转做 R5**——两需求点零文件交集,进度表以「🔄并发会话/🔄本会话」标记归属 | rd-dev R5 接续 |
| 2026-09-27 | R2 code-review 收口(大改动双轴):不通过→修 8 项——ModelScope Success:false 软失败不缓存走 502、进程缓存 512 上限满即清、市场源重复 type 校验拒绝、limit 非整数统一 400/17004、httpx follow_redirects、installs int() 兜底、死代码清理×3(#12/#13/#14);**不修 7 项记录在案**:#6 超时无总预算(httpx 无原生支持,成本>收益)、#7 缓存键不含 source base(契约字面口径 (market,q,limit),300s 窗口可接受)、#8 except Exception 折叠 502(已有分级日志)、#10 q/limit 校验 API/service 双份、#11 双适配器同构未抽 _fetch_json、#15 市场类型双注册表——后 3 项属分层/架构收敛,建议 rd-check 或后续需求点处理 | rd-dev R2 收口裁决 |
| 2026-09-27 | R3 完成:市场一键安装(POST /projects/{pid}/skills/install-remote,editor+;fetch_skill_md 双适配器拉 SKILL.md,256KB 字符上限,502/400 收口;frontmatter 强校验→同名覆盖入库 source=market+source_url 溯源,extra_files 提示支撑文件数;迁移 b8e4d2f6a9c1 skills 加 source/source_url,存量按 scope 回填);QA 18/18、三套件 66 全绿;审计通过(3 非阻断备注留痕 .scratch/R3/audit-review.md,不改代码) | rd-dev R3 收口 |
| 2026-09-27 | R5 code-review 收口(大改动双轴):15 项发现→**修 14/不修 1**——必修 6:探测子命令失败静默吞(部分结果+警告语义)、迁移双 head 归单头(部署阻断)、probe 容器去 managed 标签(消 auto-restart 竞态)、skills 只取目录、mcpServers 非 dict 按空降级、超时重试堆叠阻断(失败标记时间窗+runner wait_for);建议修 8:name str coerce、session 不钉 120s、删 _containers_api shim、测试死分支×2、抽 _read_container_json 消 inject/probe 漂移、fixture 只清 _last_result、_pick_probe_runner 对齐先例;**不修记录**:#9 并发去重无 image 键(HTTP 不传 image,latent) | rd-dev R5 收口裁决 |
| 2026-09-27 | R4 完成:市场搜索安装 Dialog(双 Tab「市场安装\|平台库」零新视觉;R1 源 Select+300ms 防抖搜索+结果列表=名/描述 truncate/安装量徽章/安装按钮;已装禁按标「已安装」+extra_files>1 支撑文件提示+成功提示需新启任务容器生效;平台库平铺列表原样迁 Tab 二不回归);tsc 零错误;审计通过(3 非阻断备注留痕 .scratch/R4/audit-review.md) | rd-dev R4 收口 |
| 2026-09-27 | R6 完成:系统级只读展示(GET /api/system-assets,JWT 两态:collected 数据/未采集 false;admin/SkillsMarket 系统级区块+超管采集钮 loading,项目 Skills/MCP 页「系统级」只读 Tab/区块标「镜像内置」);collected_at 序列化改 ISO「T」形态修 Safari new Date() Invalid Date(N1);pytest 18 passed + tsc 零错误;审计通过(备注留痕 .scratch/R6/audit-review.md) | rd-dev R6 收口 |
| 2026-09-27 | R7 完成:对话 /skills /mcp 候选合并系统级——/skills 并入系统内置(同名项目配置优先,「内置」徽标仅插引用不可调)、/mcp 补全照 /skills 模式新做(触发词先于 / 判定,选中插入 @mcp:名称)、系统级未采集回退现状,零新视觉;tsc 零错误;审计通过(3 条 info 留痕)——**R1-R7 全 ✅ 收官**(待 rd-check 全量校验) | rd-dev R7 收口 |
