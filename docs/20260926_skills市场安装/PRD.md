# PRD:项目 Skills 市场搜索与安装(find-skills 能力内置化)

> 创建日期:2026-09-26
> 状态:**已确认**(参照实现=@vercel-labs/find-skills,端点全部实测;待确认清单为空)
> 关联:平台主 PRD R17(项目 Skills);调研基线:skills.sh 公开 API + ModelScope Skills API(均免鉴权,已 curl 实测)

## 背景与目标

项目 Skills 管理 目前只能从「平台官方库」安装或手动上传 .md。用户希望在项目内**直接搜索外部市场并一键安装**,等效于 vercel-labs find-skills skill 的能力(搜索 skills.sh/ModelScope 市场、按需安装),把找 skill→装 skill 的链路收进平台。

## 用户故事

1. 作为项目 editor,我希望在 Skills 管理里搜索市场中的 skill(如「pdf 处理」),以便发现可复用能力
2. 作为项目 editor,我希望一键安装搜索到的 skill,以便它在任务的 Claude 容器中直接生效

## 事实基线(调研实证,实现照此接线)

- 搜索:skills.sh `GET https://skills.sh/api/search?q=&limit=[&owner=]`(免鉴权,返回 name/description/installs/owner/repo);ModelScope `PUT https://modelscope.cn/api/v1/dolphin/skills` body `{Query,PageSize,PageNumber}`(**过滤字段是 Query**,Name 无效)
- 安装源文件:skills.sh `GET https://skills.sh/api/download/{owner}/{repo}/{slug}` → `{files:[{path:"SKILL.md",contents}]}`;ModelScope `GET https://modelscope.cn/skills/{Path}/{Name}/resolve/master/SKILL.md` → SKILL.md 全文
- 安装单元:含 SKILL.md 的目录,最小=单 SKILL.md;find-skills 本体即单文件
- 平台注入:skills 入库即自动进 `list_project_skill_contents` → 容器启动 claude_inject 链,零改造;**新装 skill 需新容器生效**

## 需求点清单

### R1:市场源配置(超管)

- **描述**:内置双市场源(ModelScope、skills.sh),源清单存 `platform_settings` 键 `skill_market_sources`(JSON:名称/类型/base),超管可在平台设置页维护;默认预置两源
- **前置条件**:超管登录
- **边界定义**:
  - 做什么:源的增删改(名称+类型 modelscope|skillssh+base);普通用户只读可见源列表
  - 不做什么:不做自定义索引格式(仅内置两种类型的适配器);不做源级鉴权配置
- **字段定义**:
  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | name | string | 是 | 展示名(如 ModelScope) |
  | type | enum modelscope/skillssh | 是 | 适配器类型 |
  | base | string | 是 | 市场基地址(https 开头) |
- **依赖**:无
- **异常与边界场景**:base 非 https 拒绝;删除已被引用的源不阻止(历史安装条目保留 source 记录)
- **验收标准**:超管增删源生效;项目侧搜索 Dialog 可见源列表

### R2:市场搜索接口(后端代理)

- **描述**:`GET /api/skills/market/search?market={name}&q={query}&limit=`——后端代理调用市场搜索端点,统一响应
- **前置条件**:登录用户(JWT);market 必须在源列表
- **边界定义**:
  - 做什么:后端 httpx 代理(免 CORS);ModelScope 走 dolphin PUT、skills.sh 走 GET /api/search;归一化响应 `[{name, description, installs|downloads, ref(安装用标识), market}]`;limit 默认 20 上限 50;5s 超时;结果缓存 5 分钟(内存)
  - 不做什么:不做跨源聚合排序(按源独立返回,前端 Tab 或下拉切源);不做全文内容搜索
- **字段定义**(归一化条目):
  | 字段 | 类型 | 说明 |
  |---|---|---|
  | name | string | skill 名 |
  | description | string | 描述(market 未返回则空) |
  | installs | int | 安装量(skills.sh=installs,ModelScope=DownloadCount) |
  | ref | string | 安装标识(modelscope: `{Path}/{Name}`;skillssh: `{owner}/{repo}/{slug}`) |
  | market | string | 源名 |
- **依赖**:R1
- **异常与边界场景**:市场端点超时/5xx → 502「市场暂不可用」;q 为空 → ModelScope 语义返回全库列表,前端强制 q 必填;结果 0 → 空数组
- **验收标准**:两个真实市场各搜一次均有结果;超时降级不 5xx 挂死

### R3:一键安装到项目

- **描述**:`POST /api/projects/{pid}/skills/install-remote` body `{market, ref}`——后端拉取 SKILL.md → 复用现有 frontmatter 校验 → 入库(scope=project)+写 project_skills 关联
- **前置条件**:项目 editor+(沿用现有安装权限);market/ref 合法
- **边界定义**:
  - 做什么:按源拉 SKILL.md(modelscope resolve / skills.sh api/download 取 files 中 path=SKILL.md 的 contents)→ parse_skill_markdown 校验 name/description/kebab-case → 同名覆盖更新(沿用 upload 语义)→ 记录来源;文件数>1 时提示「含 N 个支撑文件,仅安装 SKILL.md」;写审计
  - 不做什么:不装多文件(脚本资源不拉);不做版本锁定/更新检查(二期)
- **字段定义**(skills 表扩展,alembic 迁移):
  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | source | enum platform/project/market | 是 | 新增,存量行回填按现 scope 映射 |
  | source_url | string | 否 | 市场来源 URL(modelscope resolve / skills.sh download) |
- **依赖**:R1、R2
- **异常与边界场景**:SKILL.md 拉取失败 → 502;frontmatter 校验失败 → 400 带原因;与现有项目 skill 同名 → 覆盖并提示;content 大小上限 256KB 超限拒绝
- **验收标准**:
  1. 从 ModelScope 安装 @vercel-labs/find-skills → 项目列表出现,source=market
  2. 从 skills.sh 安装任意 skill → 同上
  3. 同名重复安装 → 覆盖更新不重复建行
  4. viewer 安装 → 403
  5. 安装后新启任务容器,skill 文件出现在 /root/.claude/skills/(注入链验证)

### R4:前端市场 Dialog 改造

- **描述**:SkillsManagement「从市场安装」Dialog 从平铺平台库改为「源选择 + 搜索框 + 结果列表(名/描述/安装量/安装按钮)+已装标记」;保留「平台库」切换 Tab(官方库安装沿用);安装成功提示「需新启任务容器生效」
- **前置条件**:R1-R3
- **边界定义**:搜索框 300ms 防抖(复用 useDebounce);已安装(ref 命中已装列表)标「已安装」禁按;加载/超时/空态文案齐全
- **依赖**:R1-R3
- **验收标准**:搜索→安装→列表出现全链路可走;UI 沿用现有 Dialog/Table/bdg 体系零新视觉

## 非功能需求

- 市场拉取强制后端代理(免 CORS/统一超时缓存/审计);市场内容是 prompt 注入面——入库前强制 frontmatter 校验+256KB 上限+审计留痕

## 范围外

- 多文件 skill 完整安装(仅 SKILL.md,提示支撑文件数)
- skill 版本锁定与 update/check(find-skills 的 update 能力,二期)
- 自定义索引格式市场(index.json),仅内置两种适配器
- 钉钉/通知类集成

## 设计稿引用

- 无外部设计稿;Dialog/列表沿用 SkillsManagement 现有样式(globals.css 体系)

## 确认记录(2026-09-26)

| 事项 | 结论 |
|---|---|
| 参照实现 | @vercel-labs/find-skills(搜索+安装能力内置化) |
| 市场源 | 内置 ModelScope + skills.sh 双源,超管可配置(platform_settings) |
| 搜索执行 | 后端代理(免 CORS/缓存/审计) |
| 安装单元 | 仅 SKILL.md 单文件(平台单文件模型零改造);多文件提示不完整 |
| 安装权限 | 项目 editor+(沿用现有) |

## 待确认清单

(空——参照实现与端点已实测,边界随参照实现收口)
