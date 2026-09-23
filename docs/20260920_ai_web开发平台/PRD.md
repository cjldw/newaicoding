# PRD:AI Web 开发平台

> 创建日期:2026-09-20
> 状态:**打磨中**(2026-09-23 增量4:新增 R28 用户信息修改增强 / R29 平台导览 / R30 黑白主题切换)
> 参考形态:MonkeyCode(流程) × v0.dev / bolt.new(AI 工作台) × GitHub Codespaces(容器) × rd-flow(需求打磨)

## 背景与目标

为**内部团队/企业**提供一个 Web 平台,承载完整的 **AI 驱动研发流程**:**需求打磨 → 开发 → 测试 → 发布 → 归档**。每个阶段的执行体是**任务**,任务在**任务级容器**中由 **Claude(平台 Agent SDK 主路径 + 容器内 Claude CLI 辅助)与人协同完成**,全程在浏览器内闭环。

**解决什么问题:**
- 需求/代码/测试/发布上下文分散在 IM、文档、Git、CI 各处,无法追溯
- 非研发角色无法直接驱动 AI 完成开发任务
- AI 产出不可审计、不可复现,团队不敢用
- 流程沉淀(为什么这么做、踩了什么坑)随人走

**成功衡量:**
- 一个需求从录入到发布上线,**全流程在平台内完成**
- 每个任务的**对话、终端、文件变更、Git 提交**全程留痕可回放
- **所有流程产物(PRD / 测试报告 / 部署说明 / 归档总结)commit 到 GitLab**,代码与文档同仓库、同分支、同评审
- 归档后自动产出**知识条目**,后续项目可检索复用
- 用户从"我有一个需求"到"看到预览 URL"**< 5 分钟**

## 用户故事

1. 作为 **项目负责人**,我希望创建一个项目并绑定 GitLab 仓库,以便代码资产集中管理
2. 作为 **产品/需求方**,我希望录入需求后,AI 在容器里**协助打磨需求**并生成 `docs/{需求}/PRD.md`,以便需求可被开发直接消化
3. 作为 **评审人**,我希望在平台上看到 AI 打磨后的 PRD,确认后一键标记"评审通过",PRD 自动 commit 到需求分支
4. 作为 **开发负责人**,我希望基于已通过评审的需求创建开发任务,让 AI 在需求分支上完成编码
5. 作为 **任何成员**,我希望在任务执行时看到 Claude 终端实时输出、文件改动、预览效果,以便了解 AI 在做什么
6. 作为 **测试负责人**,我希望基于需求验收标准创建测试任务,AI 协助生成/执行测试用例并产出报告(commit 到需求分支)
7. 作为 **发布负责人**,我希望测试通过后创建发布任务,把需求分支 merge 到 master 并部署到对外地址
8. 作为 **团队**,我希望发布完成后整个流程自动归档,沉淀到知识库,以便后续检索复用

## 核心概念模型

```
项目 (Project)
 ├── GitLab 仓库绑定(每项目一个 repo)
 ├── 模型配置(项目级 url+key)
 ├── 成员(owner / editor / viewer)
 │
 └── 需求 (Requirement)           ← 流程起点
      ├── 需求分支 `req-{reqId}`(创建需求时从 master 切出)
      ├── 状态机:draft → polishing → reviewing → approved → in_progress → done → archived
      │
      └── 1:N 任务 (Task),所有任务默认在需求分支 `req-{reqId}` 上工作
           │
           ├── 打磨任务 (type=requirement)
           │    ├── AI 协助打磨需求,产出 docs/{doc_dir}/PRD.md
           │    └── 评审通过 → PRD commit 到 req-{reqId}
           │
           ├── 开发任务 (type=dev)
           │    ├── AI 编码 → 文件变更 + git commit → push 到 req-{reqId}
           │    └── 状态机:pending → running → done / failed / cancelled
           │
           ├── 测试任务 (type=test)
           │    ├── AI 生成测试用例 → 人审 → AI 执行 → 产出 docs/{doc_dir}/report.md
           │    ├── 报告 commit 到 req-{reqId}
           │    └── 状态机:pending → cases_review → running → passed / failed(可驳回回开发)
           │
           └── 发布任务 (type=release)
                ├── git merge req-{reqId} → master
                ├── 执行发布脚本
                ├── 部署产物 commit 到 master 的 docs/{doc_dir}/
                └── 生成互联网可访问地址 http://{slug}.{deploy_base_domain}:{port}(根域名取平台设置,发布任务可自定义对外域名,Q28/Q29)

需求 done(所有发布任务 deployed)→ 触发归档 → docs/{archive_dir}/summary.md commit 到 master + 知识库
```

**分支模型**:
- 需求创建时,平台在 GitLab 上自动建分支 `req-{reqId}`(从 master)
- 该需求下所有任务**默认在 `req-{reqId}` 分支上工作**(保证一个需求代码统一)
- 任务创建时**可自定义基础分支**(特殊情况:如紧急修复直接从 master 切)
- 多任务并行push:**Git 乐观锁**——先提交先得,后提交需 pull/rebase;冲突 AI 自动解决,失败则人工在任务终端介入

**文档目录规范**(2026-09-21 Q26 修订,全局统一):
- 平台产出的**全部流程文档**统一落在 `docs/` 下,任务级目录 **`docs/{YYYYMMDD}_{descSlug}_{taskShortId}/`**(下称 `{doc_dir}`):
  - `{YYYYMMDD}` = 任务创建日期
  - `{descSlug}` = 所属需求标题 slug 化:保留中文,空格/特殊字符转 `-`,截断 32 字符
  - `{taskShortId}` = 任务 uuid 前 8 位,平台内唯一(碰撞自动追加 `-1`)
  - **目录名在任务创建时生成并固定**,完整路径随任务字段记录(prd_file_path / report_file_path / deploy_log_path)
- 归档总结目录(系统生成,无任务):**`docs/{YYYYMMDD}_{descSlug}_archive/`**(下称 `{archive_dir}`),日期为归档当天
- 各产物路径:PRD → `{doc_dir}/PRD.md`(打磨任务);测试报告 → `{doc_dir}/report.md` + `cases.json`(测试任务);部署产物 → `{doc_dir}/` 下 CHANGELOG.md + deploy-log.txt(发布任务);归档总结 → `{archive_dir}/summary.md`(系统)

**任务执行工作台**(打开任何任务即进入):

```
┌────────────────────────────────────────────────────┐
│ 任务头:标题 / 类型 / 状态 / 操作(停止/驳回/通过) │
├──────────┬─────────────────────────┬───────────────┤
│ 文件树   │  Monaco 编辑器          │  Claude 终端  │
│          │  (实时同步容器)         │  (Web TTY)    │
│          │                         │               │
│          ├─────────────────────────┤               │
│          │  Diff 视图 / 预览 iframe │               │
└──────────┴─────────────────────────┴───────────────┘

文件树面板提供「全部文件 / 变更文件」双视图:变更视图列出本任务改动文件(类型 + 行数标注),供快速核查(R11,Q27)。
```

## 需求点清单

### R1:用户与账号体系

- **描述**:平台基础账号系统 + **GitLab 个人 token 绑定**(任务执行用)
- **触发场景**:首次访问 / 会话过期 / 个人设置页绑定 GitLab
- **前置条件**:无
- **边界定义**:
  - 做什么:
    - **手机号+密码注册/登录**、找回密码(V2 短信验证码)、登出、修改本人密码/昵称/头像
    - **GitLab 个人 token 绑定/解绑/重新绑定**:任务执行(clone/pull/push/commit)使用用户自己的 token,确保 GitLab 侧操作可追溯到人
  - 不做什么:第三方 OAuth、SSO、邮箱验证、GitLab OAuth(仅用 personal access token);**V1 不接短信服务商**(预留字段与接口,短信功能 V2 再做)
- **字段定义**(User):
  | 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
  |---|---|---|---|---|---|
  | phone | string(11) | 是 | - | 合法手机号(中国:`^1[3-9]\d{9}$`),全局唯一 | 登录名/找回密码 |
  | password | string | 是 | - | ≥8 位含字母+数字,bcrypt 存储 | 不明文 |
  | nickname | string(32) | 否 | =phone | - | |
  | avatar_url | string(255) | 否 | 默认头像 | URL | |
  | status | enum | 是 | active | active/disabled | |
  | **role** | enum | 是 | user | superadmin / user | 平台角色;超管可多人(Q4),平台管理功能仅超管可用(R19) |
  | **gitlab_username** | string(64) | 否 | null | - | GitLab 上的用户名(绑定时从 GitLab 拉取) |
  | **gitlab_token_encrypted** | string | 否 | null | AES-GCM 加密 | personal access token,接口永不回显完整 |
  | **gitlab_token_scopes** | json | 否 | null | - | 用户授权的 scope 列表(read_repository/write_repository/api) |
  | **gitlab_token_bound_at** | datetime | 否 | null | - | 绑定时间 |
  | created_at | datetime | 是 | now | - | |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 注册重名 | 拒绝并提示字段 | 停留注册页 |
  | 密码错 5 次 | 锁 10 分钟 | 返回倒计时 |
  | **找回密码(V2)** | **短信验证码**(6 位数字,10 分钟有效) | 重置页 |
  | 登录成功 | JWT(access 2h + refresh 7d) | Dashboard(R21;项目列表经导航可达) |
  | **绑定 GitLab token** | 用户粘贴 token → 平台调 `GET /user` 验证 → 校验 scope 含 `read_repository`+`write_repository` → 保存 username 与 scopes | 绑定成功 |
  | **token scope 不足** | 提示具体缺失的 scope,拒绝绑定 | 停留绑定页 |
  | **token 失效(任务执行 401)** | 任务标记 failed,引导用户到个人设置重新绑定 | 任务列表提示 |
  | **解绑** | 清空 gitlab_* 字段;**进行中的任务不受影响**(已在容器内的 token 仍可用到任务结束) | |
- **依赖**:无
- **异常与边界场景**:
  - **短信服务不可用(V2)** → 找回密码降级"联系管理员"
  - 多处登录允许(V1 不做单点踢出)
  - phone 不可改
  - **token 加密密钥**:平台级 KMS/环境变量,V1 用单 key;若 key 泄露需全量重新绑定
  - **未绑定 token 的用户**:仅可浏览(viewer 角色不绑也能看);editor/owner 创建任务前**强制绑定**(R12)
- **验收标准**:
  1. 注册-登录-登出闭环
  2. 5 次错误触发锁定
  3. **找回密码短信可达(V2),验证码一次性**
  4. 密码无明文落盘/日志
  5. GitLab token 绑定/解绑/重绑可用
  6. scope 不足时给出明确错误
  7. token 失效时任务 failed 并引导重绑
  8. token 不明文出现在接口/日志/前端

### R2:项目管理(绑定 GitLab,支持多仓库)

- **描述**:项目是流程与资源的顶层容器;**每个项目可绑定多个 GitLab 仓库**(主代码仓库 + 测试仓库 + 其他辅助仓库)。GitLab 操作分两类:**平台管理员 bot token** 负责项目级/系统级动作(建 repo、建需求分支、merge、部署产物 commit);**用户个人 token** 负责任务执行(clone/pull/push/commit)与**评审通过时的 PRD commit**
- **触发场景**:登录后项目列表 / 新建项目
- **前置条件**:R1
- **边界定义**:
  - 做什么:
    - 项目创建时**必须绑定一个"主代码仓库"**(role=main,唯一);创建后可在项目设置中**追加绑定其他仓库**(role=test/docs/other,可多个)
    - 每个仓库两种绑定方式:
      - a) **平台自动建 repo**:用管理员配置的 GitLab bot token,在指定 group 下创建 `{slug}` / `{slug}-{suffix}` 仓库
      - b) **绑定已有 repo**:用户提供 repo URL,平台用 **bot token** 验证 repo 存在且 bot 有 read/write/merge/webhook 权限
    - 项目列表/详情/重命名/归档/删除(软删 7 天)
    - **项目级默认分支**配置(默认 `master`,可改 `main`/`develop` 等),所有仓库共享此默认分支名
    - **项目创建后,平台 bot 把项目创建者加为所有绑定 repo 的 Maintainer**(后续邀请的成员加为 Developer)
  - 不做什么:
    - **不做**多 GitLab 实例(V1 只支持一个平台配置的 GitLab)
    - **不做** GitHub / Gitee 等其他 Git 托管
    - **不做**项目模板市场
    - **不做**项目级 GitLab token(统一走平台 bot + 用户个人 token)
    - **不做**仓库级权限细分(所有绑定 repo 的权限跟随项目成员)
    - **不做** main repo 换绑(V1 只能删项目重建)
- **字段定义**(Project):
  | 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
  |---|---|---|---|---|---|
  | project_id | uuid | 是 | auto | - | |
  | name | string(64) | 是 | - | 同用户下唯一 | 显示名 |
  | slug | string(64) | 是 | 自动生成 | 全局唯一,小写字母数字- | 子域/主仓库名 |
  | description | string(255) | 否 | "" | - | |
  | default_branch | string(64) | 是 | master | - | 项目默认分支,所有仓库的需求分支从这里切 |
  | visibility | enum | 是 | private | private/internal | |
  | owner_id | ref(R1) | 是 | 创建者 | - | |
  | status | enum | 是 | active | active/archived/deleted | |
  | created_at / updated_at | datetime | 是 | now | - | |

  **字段定义**(ProjectRepo,项目与仓库的关联表,1:N):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | repo_id | uuid | 是 | auto | 平台内部 id |
  | project_id | ref | 是 | - | |
  | role | enum | 是 | - | main(唯一)/ test / docs / other |
  | gitlab_repo_url | string(255) | 是 | - | |
  | gitlab_repo_id | int | 是 | - | GitLab 内部 id |
  | gitlab_bind_type | enum | 是 | auto | auto(平台建)/ manual(用户绑) |
  | created_by | ref(R1) | 是 | - | 绑定时操作人 |
  | created_at | datetime | 是 | now | |

  **约束**:`role=main` 的仓库**每项目唯一**;`test`/`docs`/`other` 可有多个;单项目绑定 repo 数 ≤ 10。

  **GitLab token 分工**(不存字段,仅规则):
  | 操作 | 使用 token | 说明 |
  |---|---|---|
  | 创建项目(auto 建 repo) | **平台 bot token** | 在指定 group 下建 repo |
  | 绑定已有 repo(manual) | **平台 bot token** | 验证 repo 存在且 bot 有权限 |
  | 创建需求分支 `req-{reqId}` | **平台 bot token** | **在所有绑定 repo 上建同名分支** |
  | 邀请项目成员 | **平台 bot token** | 把成员加为**所有绑定 repo** 的 Developer |
  | **任务执行**(clone/pull/push/commit) | **创建任务的用户个人 token** | GitLab 侧操作可追溯到人 |
  | **需求评审通过 commit PRD** | **评审通过操作人的个人 token** | 评审是人的动作,可追溯;commit 到 `main` repo 的 `req-{reqId}` 分支 |
  | 发布任务 merge `req-{reqId}` → `master` | **平台 bot token** | 系统动作,不依赖用户在线;**所有绑定 repo 都执行 merge** |
  | 部署产物 commit 到 master | **平台 bot token** | 系统动作;commit 到 `main` repo |
  | GitLab API 只读查询 | **平台 bot token** | 只读,稳定 |
  | GitLab webhook 接收 | webhook secret(非 token) | 每个 repo 一个 webhook |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | auto 创建项目 | 平台 bot 建 main repo + 初始化默认分支 + README + 把创建者加为 Maintainer | 进入项目详情 |
  | manual 绑定 main repo | 平台 bot 验证 repo 存在且 bot 有权限 + 把创建者加为 Maintainer(若已是成员则跳过) | 失败拒绝 |
  | 追加绑定 test/docs/other repo | 在项目设置 → 仓库 Tab → "添加仓库";同 manual 流程;role 必填;同一 repo 不可重复绑定到同一项目 | |
  | 解绑仓库 | **仅 role ≠ main 可解绑**;main 不可解绑;解绑后**不动 GitLab repo**(仅断关联) | |
  | 邀请成员到项目(R12) | 平台 bot 把该用户加到**所有绑定 repo**为 Developer | 成员可用个人 token 访问所有 repo |
  | 移除项目成员 | 平台 bot 把该用户从**所有绑定 repo**移除 | |
  | 删除项目 | 软删 7 天,7 天后**不动 GitLab repo**(只删平台记录/容器/部署) | 列表隐藏 |
  | 归档项目 | 容器停止、部署下线、只读 | 列表灰显 |
  | 平台 bot token 失效 / 未配置 | 项目创建/分支管理/merge/成员同步全部失败 → **项目创建入口禁用**,超管到"用户中心 → 平台设置"配置 | 超管告警 |
  | 用户个人 token 失效 | 该用户创建的任务 failed,引导重新绑定(R1) | 不影响其他用户 |
- **依赖**:R1
- **异常与边界场景**:
  - 平台 GitLab 实例地址 + bot token + webhook secret 在**用户中心 → 平台设置**(超管)配置;**未配置时项目创建入口禁用**
  - slug 冲突自动加后缀 `-xxxx`
  - 单用户项目数 ≤ 50
  - **成员在 GitLab 上的 username 与平台 username 可能不同**:以 GitLab username 为准(用户绑定时已拉取)
  - 成员被移除后,其 GitLab repo 权限也被移除,但**该用户已提交的 commit 历史保留**(Git 天然特性)
  - 平台 bot token 配置变更:即时生效,无需重启
  - 追加绑定的 repo 若已存在分支 `req-{reqId}`(历史遗留),平台**复用**该分支,不报错
- **验收标准**:
  1. auto 模式建项目后,GitLab 上能看到对应 repo 与默认分支,创建者是 Maintainer
  2. 追加绑定 test repo 后,项目详情可见两个 repo
  3. main repo 不可解绑;test/docs 可解绑
  4. 平台 bot token 失效/未配置时项目创建失败并告警
  5. 邀请成员后,该成员能用个人 token clone 所有绑定仓库
  6. 移除成员后,该成员 token 无法访问仓库
  7. 创建需求时,所有绑定 repo 上都建了 `req-{reqId}` 分支

### R3:需求管理与打磨

- **描述**:流程起点。需求**创建后进入"打磨"阶段**:平台启动**打磨任务**(一种特殊任务),AI 在容器内与用户对话,产出 `docs/{doc_dir}/PRD.md`(文档目录规范见核心概念模型);**评审通过后 PRD commit 到需求分支**
- **触发场景**:项目内 → 需求 Tab → 新建需求
- **前置条件**:R2;R13 模型已配置
- **边界定义**:
  - 做什么:
    - 需求 CRUD + 状态机
    - 创建需求时**自动在 GitLab 建分支 `req-{reqId}`**(从项目默认分支切出)
    - 打磨任务:AI 与用户对话,产出 PRD 草稿(写入容器,未 commit)
    - 评审:owner/editor 在平台上点击"评审通过/驳回";通过则 PRD commit 到 `req-{reqId}` 分支;驳回填理由,回到打磨
    - 需求下可看到所有关联任务
  - 不做什么:
    - **不做**评审会议/通知(V1 仅平台内点击)
    - **不做**需求优先级看板/排期(V2)
    - **不做**需求变更版本对比(改内容 → 驳回重审)
- **字段定义**:
  | 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
  |---|---|---|---|---|---|
  | req_id | uuid | 是 | auto | - | |
  | project_id | ref(R2) | 是 | - | - | |
  | title | string(128) | 是 | - | - | |
  | background | text | 否 | - | Markdown | 为什么做 |
  | description | text | 是 | - | Markdown | 做什么(初始草稿) |
  | acceptance_criteria | text | 否 | - | Markdown,勾选清单 | 怎么算完成(打磨中完善) |
  | req_branch | string(64) | 是 | `req-{reqId}` | 同 repo 唯一 | 需求分支名,可自定义 |
  | prd_file_path | string(255) | 是 | `docs/{YYYYMMDD}_{descSlug}_{taskShortId}/PRD.md` | - | PRD 在 repo 内的路径;打磨任务创建时生成并固定 |
  | status | enum | 是 | draft | draft/polishing/reviewing/approved/in_progress/done/archived/rejected | |
  | priority | enum | 是 | medium | low/medium/high | V1 仅展示用 |
  | created_by | ref(R1) | 是 | - | |
  | reviewed_by | ref(R1) | 否 | null | | |
  | reviewed_at | datetime | 否 | null | | |
  | reject_reason | text | 否 | null | 驳回时必填 | |
  | polish_task_id | ref(R4) | 否 | null | 当前打磨任务 | |
- **交互规则**(状态机):
  | 当前状态 | 触发 | 目标状态 | 规则 |
  |---|---|---|---|
  | (创建) | 用户填 title/description | draft | 后台异步建 GitLab 分支 `req-{reqId}` |
  | draft | 点击"开始打磨" | polishing | 启动打磨任务(拉起容器 + Claude 会话) |
  | polishing | 用户点击"提交评审" | reviewing | PRD 草稿已写入容器,未 commit |
  | reviewing | 评审通过(owner/editor) | approved | **PRD commit + push 到 req-{reqId} 分支,使用评审通过操作人的个人 GitLab token**,容器销毁 |
  | reviewing | 驳回(owner/editor) | polishing | 填 reject_reason,重新打磨 |
  | approved | 第一个开发任务启动 | in_progress | 自动 |
  | in_progress | 所有发布任务 deployed | done | 自动 |
  | done | 归档完成 | archived | 自动(R7) |
  | 任意非 archived/done | 取消 | rejected | owner 操作,填理由;GitLab 分支保留(只读) |

- **依赖**:R2、R4(打磨任务)、R13
- **异常与边界场景**:
  - 打磨任务同一时间一个需求**只能有一个**
  - 评审中需求不可编辑 title/description(避免评审过程中改需求)
  - 驳回后可继续打磨,再次提交评审;reviewed_by/reject_reason 保留历史
  - 需求已有任务进行中(approved 之后),不可驳回,只能"取消"
  - 取消需求后,GitLab 分支**保留 30 天**,到期平台自动删除(避免误删代码)
- **验收标准**:
  1. 创建需求后 GitLab 上能看到对应分支
  2. 打磨任务能在容器内启动 AI 会话
  3. 评审通过后 PRD 出现在 `req-{reqId}` 分支的 `prd_file_path` 指定路径
  4. 评审通过前无法创建开发任务

### R4:任务(统一执行单元)

- **描述**:所有流程阶段(打磨/开发/测试/发布)的执行体都是**任务**。任务在**任务级容器**中运行,任务结束(成功/失败/取消)容器销毁。**任务对话框支持上传文件到容器 `/tmp/uploads/{task_id}/`,AI 可用 `@文件名` 引用文件内容**
- **触发场景**:从需求详情点击"创建任务"(不同类型入口不同)
- **前置条件**:R3(需求已建);R13(模型已配);**R1(创建任务的用户已绑定 GitLab 个人 token,且 token 对该 repo 有 read+write 权限)**
- **边界定义**:
  - 做什么:
    - 四种任务类型:**requirement(打磨)/ dev(开发)/ test(测试)/ release(发布)**,通过 `type` 区分
    - 任务创建时**拉起专属容器**,容器内 `git clone` + `checkout` 到指定分支
    - AI 在容器内执行(读写文件/跑命令/git 操作)
    - **任务对话框支持上传文件**(附件按钮 + 拖拽),文件上传到容器 `/tmp/uploads/{task_id}/`
    - **AI 引用文件**:用户在对话框输入 `@filename.txt`,平台自动补全当前任务已上传的文件;`< 100 KB` 的文件**自动注入内容到 prompt**,`≥ 100 KB` 的文件**只给路径**,AI 用工具(read_file)自己读
    - 任务结束(成功/失败/取消/超时)**销毁容器**(上传的文件随之丢失)
    - 任务产物(代码/文档)**全部通过 git commit + push 持久化到 GitLab**
  - 不做什么:
    - **不做**任务指派到人(谁创建谁负责)
    - **不做**任务子任务拆解(在 R3 需求打磨阶段定义)
    - **不做**任务模板市场/编排 DAG
    - **不做**上传文件持久化到 GitLab(临时文件;若需保留,引导用户让 AI 把内容写入正式文件并 commit)
    - **不做**文件类型白名单(不限制,AI 自行判断;但禁止上传 > 50MB 的文件)
- **字段定义**(Task 主表):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | task_id | uuid | 是 | auto | |
  | req_id | ref(R3) | 是 | - | 所属需求 |
  | project_id | ref(R2) | 是 | - | 冗余便于查询 |
  | type | enum | 是 | - | requirement / dev / test / release |
  | title | string(128) | 是 | - | |
  | description | text | 是 | - | 本次要做什么(AI 的输入) |
  | base_branch | string(64) | 是 | =req.req_branch | **基础分支**(从哪里切/直接在哪个分支工作) |
  | work_branch | string(64) | 是 | =base_branch | **工作分支**(默认=基础分支;特殊情况可新建) |
  | status | enum | 是 | pending | pending/running/done/failed/cancelled/timeout |
  | container_id | string | 否 | null | 任务运行时的 docker id |
  | runner_id | ref(R16) | 否 | null | **任务运行的 Runner**(D6 改为 Runner 架构) |
  | conversation_id | uuid | 是 | auto | 关联 Claude 会话 |
  | created_by | ref(R1) | 是 | - | |
  | started_at / finished_at | datetime | 否 | - | |
  | total_tokens_in / total_tokens_out | int | 是 | 0 | |
  | error_message | text | 否 | null | failed/timeout 时填 |
  | last_commit_sha | string(40) | 否 | null | 任务结束时最后 commit |

  **字段定义**(TaskUploadedFile,任务上传文件表):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | file_id | uuid | 是 | auto | |
  | task_id | ref(R4) | 是 | - | |
  | filename | string(255) | 是 | - | 原始文件名 |
  | stored_filename | string(255) | 是 | - | 容器内实际文件名(冲突自动重命名,如 `file-1.txt`) |
  | size | int | 是 | - | 字节 |
  | mime_type | string(64) | 是 | - | |
  | container_path | string(255) | 是 | `/tmp/uploads/{task_id}/{stored_filename}` | |
  | uploaded_by | ref(R1) | 是 | - | |
  | uploaded_at | datetime | 是 | now | |

  **字段定义**(TaskMessage,任务消息表,存对话历史):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | message_id | uuid | 是 | auto | |
  | task_id | ref(R4) | 是 | - | |
  | role | enum | 是 | - | user / assistant / tool |
  | content | text | 是 | - | Markdown;`@filename` 在前端渲染为可点击链接 |
  | file_refs | json | 否 | null | `[{file_id, filename, container_path, injected: bool}]`;`injected=true` 表示内容已注入 prompt |
  | tool_calls | json | 否 | null | `[{name, args, result, duration_ms}]` |
  | tokens_in / tokens_out | int | 否 | 0 | |
  | created_at | datetime | 是 | now | |

- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 创建任务 | 校验需求状态合法(如 dev 要求需求 approved);**校验创建者已绑定 GitLab token 且对所需 repo 有 read+write 权限**;**调度器选择 Runner**(R16);Runner 上拉起容器;**clone 主仓库到 `/workspace/main`** + **clone 所有 role=test 仓库到 `/workspace/tests/{repo_slug}`** + **clone role=docs/other 仓库到 `/workspace/{role}/{repo_slug}`**;每个仓库都 `checkout base_branch` + `git checkout -b work_branch`(若 ≠ base);启动 Claude 会话 | running |
  | AI 执行中 | 文件变更/命令执行/工具调用 实时推送到工作台;AI 工作目录默认 `/workspace/main`(主仓库),可跨目录访问其他仓库 | 用户可见 |
  | **上传文件** | 用户在任务对话框**点附件按钮或拖拽** → 前端上传到平台 → 平台转发到容器 `/tmp/uploads/{task_id}/`(同名自动重命名为 `{name}-1.txt`)→ 写 `task_uploaded_files` 表 → 前端显示附件列表 | 文件出现在对话框下方 |
  | **上传限制** | 单文件 ≤ 50MB;单次 ≤ 10 个;单任务累计 ≤ 200MB;超限拒绝 | 前端提示 |
  | **`@文件` 引用** | 用户在对话框输入 `@` → 前端自动补全当前任务已上传的文件名;选中后插入 `@filename`;发送时平台解析 `@filename` → 查 `task_uploaded_files` → **< 100KB 注入内容到 prompt** + **≥ 100KB 只注入路径**;`file_refs` 记录引用关系 | AI 收到文件内容或路径 |
  | **下载文件** | 用户点击对话框/文件列表中的文件名 → 平台从容器拉取文件流回前端 | 浏览器下载 |
  | AI 完成一段工作 | **对每个有改动的仓库**:`cd /workspace/{path} && git add -A && git commit -m "[ai:{type}] {task_title}"`(commit author = 创建任务的用户 GitLab username,committer 平台 AI 标识) | 分支有新提交 |
  | AI push | **对每个有改动的仓库**:`git push origin {work_branch}`(用**用户 token**) | 同步到 GitLab,GitLab 侧显示该用户 push |
  | push 冲突(他人在先) | AI 自动 `git pull --rebase` 或 `git merge`,解决冲突后再 push;失败则通知用户人工介入(在任务终端) | 或 failed |
  | 用户手动停止 | Claude 中断 → 通知 Runner 销毁容器 | cancelled(未 push 的改动丢失) |
  | 任务完成 | 最后一次 commit + push(**所有有改动的仓库**)→ 标记 done → 通知 Runner 销毁容器 | done |
  | 任务失败/超时 | 标记失败原因 → 通知 Runner 销毁容器 | failed/timeout |
  | 销毁容器前检查 | 若任一仓库的 work_branch 有未 push 的 commit → **强制 push**(用**用户 token**) | |
  | **用户 token 失效(401)** | 任务标记 failed,error_message 提示"GitLab token 失效,请重新绑定";容器销毁 | 引导到 R1 个人设置 |
  | **Runner 离线** | Runner 心跳超时(60s)→ 标记 Runner offline;其上的 running 任务**不动**(容器还在跑,只是平台无法通信);Runner 恢复后重新上报容器状态 | Runner 列表显示 offline |
  | **Runner 上的任务超时** | 任务超时销毁兜底(60 分钟),即使 Runner offline,Runner 恢复后也会收到销毁指令 | |
- **依赖**:R3、R8、R13、R16
- **异常与边界场景**:
  - 单任务最长执行 **60 分钟**,超时自动 cancel(销毁前强制 push)
  - 单项目**并发 running 任务 ≤ 3**(超出排队)
  - 同需求分支并行任务 push 冲突:AI 自动 rebase;冲突文件超过 5 个或冲突复杂 → 任务 failed,提示人工
  - 分支命名冲突:自动追加 `-{short_uuid}`
  - 容器异常崩溃:任务标记 failed,Runner 自动清理;未 push 的改动丢失(因为没 commit)
  - **用户 token 无效/权限不足**:创建任务时即拒绝,提示"请到个人设置绑定有效 GitLab token";任务执行中失效则任务 failed
  - **Runner 全部离线**:任务创建时**排队等待**,直到有 Runner 上线;前端显示"等待可用 Runner"
  - **文件上传失败**(容器不可达/磁盘满):前端提示"上传失败,请重试";任务不失败
  - **同名文件冲突**:自动重命名 `file.txt` → `file-1.txt` → `file-2.txt`,在前端显示实际存储名
- **验收标准**:
  1. 创建任务后容器 30s 内拉起(在某个 Runner 上)
  2. AI 修改的文件能通过 git log 在 GitLab 看到
  3. push 冲突时 AI 能自动 rebase,失败能通知人工
  4. 任务结束后容器被销毁
  5. 销毁前未 push 的 commit 被强制 push
  6. **文件上传成功,AI 能通过 `@filename` 读取文件内容**
  7. **文件上传 ≥ 100KB 时,AI 收到的是路径而非内容**
  8. **Runner offline 时任务排队,Runner 恢复后继续执行**

### R5:开发任务(type=dev)

- **描述**:基于已通过评审的需求,AI 在需求分支上完成编码;**产出物仅是代码 commit**,不单独建 MR(评审走最终发布时的整体 merge)
- **触发场景**:需求详情(status=approved)→ "创建开发任务"
- **前置条件**:R3 status=approved;**同需求下没有 running 状态的打磨任务**
- **边界定义**:
  - 做什么:
    - 一个需求可创建**多个开发任务**(按模块/功能拆分,**可并行**)
    - AI 在容器内编码 → 自动 commit + push 到 `req-{reqId}` 分支
    - AI 执行过程中用户可通过 Web TTY 介入(手动跑命令/改代码)
    - 开发任务可**读取同需求下的测试报告**(R6 产出),作为修复上下文
    - 工作台文件树提供**变更文件清单**快速核查入口(R11「全部/变更」双视图),AI 改动实时出现在清单中
  - 不做什么:
    - **不做**任务级 MR(MR 在 R7 发布任务时统一处理)
    - **不做**代码评审 Web 界面(评审在最终 merge 时进行)
- **字段定义**:沿用 R4 通用字段;特定字段:
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | related_test_task_id | ref | 否 | null | 若由测试驳回创建,关联原测试任务 |
  | fix_context | text | 否 | null | 驳回时携带的失败用例上下文 |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 创建 dev 任务 | 用户填 description(要让 AI 做什么) | running |
  | AI 编码 | 沿用 R4 通用规则 | |
  | 从测试驳回创建 | 自动填充 fix_context(失败用例 + 报告路径),提示 AI 优先修复 | running |
  | 需求下所有 dev 任务 done | 需求详情页"创建测试任务"按钮亮起 | - |
- **依赖**:R3、R4
- **异常与边界场景**:
  - 需求下并行 dev 任务数无硬上限(受 R4 项目级并发 3 限制)
  - AI 修改 PRD 文件(`prd_file_path`)→ 警告(PRD 是评审产物,原则上不应在 dev 任务中改)
- **验收标准**:
  1. AI 编码能 commit + push 到需求分支
  2. 测试驳回能创建携带上下文的 dev 任务
  3. 用户可在执行中通过 TTY 介入
  4. 执行中文件树变更视图实时反映 AI 改动清单,可逐文件核查(直达 Diff)

### R6:测试任务(type=test)

- **描述**:基于需求的验收标准,AI 生成测试用例 → 人审 → AI 执行。**测试任务默认拉取项目绑定的 `role=test` 仓库代码**(R2)作为测试代码,**主仓库**(`role=main`)作为被测代码;**测试报告 commit 到主仓库的需求分支** `docs/{doc_dir}/`(文档目录规范见核心概念模型);失败可驳回回开发
- **触发场景**:需求详情 → "创建测试任务"(前置:同需求下**至少一个 dev 任务 done**)
- **前置条件**:R5 同需求下至少一个 dev done
- **边界定义**:
  - 做什么:
    - **多仓库 clone**:
      - 主仓库(`role=main`)→ `/workspace/main`(被测代码)
      - 所有 `role=test` 仓库 → `/workspace/tests/{repo_slug}`(测试代码)
      - 其他仓库按需挂载到 `/workspace/{role}/{repo_slug}`
    - AI 基于主仓库 PRD 验收标准 + 当前需求分支代码 + **测试仓库现有用例**,生成/更新**测试用例清单**(人可增删改)
    - 人确认后,AI 在容器内执行测试(测试命令由 AI 根据测试仓库结构决定,如 `cd /workspace/tests/xxx && pytest`,或 `npm test`)
    - 产出**测试报告**:`docs/req-{reqId}/test-reports/{taskId}/report.md` + `cases.json`,**commit 到主仓库**需求分支;若测试脚本本身有改动,也 commit 到**对应测试仓库**的需求分支
    - **失败驳回**:创建新的 dev 任务,携带失败上下文与报告路径
  - 不做什么:
    - **不做**测试用例管理库(V1 用例只存于任务内与 repo)
    - **不做**性能测试/压测
    - **不做**第三方测试平台集成
    - **不做**测试框架强制配置(AI 根据测试仓库结构自动识别 pytest/jest/vitest 等)
- **字段定义**:沿用 R4 通用字段;特定字段:
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | based_on_dev_tasks | json | 是 | - | 关联的 dev task_id 列表 |
  | test_cases | json | 是 | - | `[{id, title, steps, expected, status, log}]` |
  | report_file_path | string | 是 | `docs/{YYYYMMDD}_{descSlug}_{taskShortId}/report.md` | 报告在主仓库内路径 |
  | test_repo_ids | json | 是 | 项目所有 role=test 的 repo_id | 本次任务挂载的测试仓库 |
  | rejected_to_dev_task_id | uuid | 否 | null | 驳回产生的新 dev 任务 |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 创建 test 任务 | 校验项目**至少绑定一个 role=test 仓库**(若无则提示先到项目设置添加);AI 读取主仓库 PRD + 当前分支代码 + 测试仓库现有用例 → 生成用例草稿 → status=cases_review | 用户编辑 |
  | 项目无 test 仓库 | 允许创建,但 AI 会**在主仓库内新建测试代码**(如 `tests/` 目录);不推荐,UI 给出提示"建议绑定独立测试仓库" | |
  | 用户确认用例 | 点击"开始执行" → AI 在容器跑 → status=running | |
  | 全部用例通过 | 生成 report.md → commit 到主仓库需求分支 + push(用用户 token)→ status=passed | 需求详情页"创建发布任务"按钮亮起 |
  | 有用例失败 | 用户选择:a) 接受失败(填豁免理由)仍 passed;b) 驳回 → 创建新 dev 任务,携带失败上下文与报告路径 | |
  | 执行异常 | status=failed,可重试 | |
- **依赖**:R5、R4、R2(多仓库)
- **异常与边界场景**:
  - AI 生成的用例人可编辑/删除/新增
  - 用例执行**串行**(V1,避免互相干扰)
  - 测试任务会写代码(测试脚本),commit 到对应仓库的需求分支
  - 测试仓库未拉取成功(token 权限不足):任务 failed,提示检查 token 对该 repo 的权限
- **验收标准**:
  1. AI 能基于 PRD 与测试仓库产出可执行用例
  2. 报告能 commit 到主仓库指定路径
  3. 测试脚本改动能 commit 到对应测试仓库
  4. 驳回能自动创建携带上下文的 dev 任务
  5. 项目无测试仓库时给出明确提示

### R7:发布任务(type=release)

- **描述**:测试通过后,把需求分支 merge 到 master,执行发布脚本,**生成互联网可访问的地址**
- **触发场景**:需求详情 → "创建发布任务"(前置:同需求下至少一个 test 任务 passed)
- **前置条件**:R6 passed
- **边界定义**:
  - 做什么:
    - 创建发布任务 → 容器内 `git checkout master && git merge req-{reqId}` → 冲突 AI 解决,失败任务 failed
    - 执行**发布脚本**(项目级配置,如 `npm run build && pm2 reload`,或平台默认:在容器内启动服务)
    - **生成对外地址**:`http://{deploy_host}:{port}`(deploy_host 默认 `{slug}.{deploy_base_domain}`,deploy_base_domain 平台设置可配;**创建发布任务时可自定义对外域名**,Q28/Q29;HTTP,端口用户自定义)
    - 部署产物(CHANGELOG / deploy-log)**commit 到 master** 的 `docs/{doc_dir}/`
    - 发布后**需求状态推进**,全部部署完成 → 需求 done → 触发归档
  - 不做什么(V1):
    - **不做** HTTPS(端口直连;含自定义域名的证书)
    - **不做**多环境(staging/prod)
    - **不做**域名级高级能力(DNS 托管 / 泛域名证书 / 多域名绑定;仅支持发布任务级设置一个对外域名)
    - **不做**外部服务器部署(SSH/K8s)
    - **不做**回滚(失败就走驳回)
    - **不做**蓝绿/金丝雀
- **字段定义**:沿用 R4 通用字段;特定字段:
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | target_env | enum | 是 | subdomain | V1 仅 HTTP 单环境 |
  | deploy_host | string | 是 | `{slug}.{deploy_base_domain}`(deploy_base_domain 来自平台设置,Q28) | 对外主机名,合法主机名格式,全平台唯一;**创建发布任务时可自定义覆盖**(Q29,需将域名解析到网关/Runner) |
  | deploy_url | string | 是 | `http://{deploy_host}:{port}` | - | 运行时拼接 |
  | deploy_port | int | 是 | - | 用户自定义,范围 10000-10099 |
  | deploy_script | text | 是 | 项目默认 | 用户可改 |
  | deploy_log_path | string | 是 | `docs/{YYYYMMDD}_{descSlug}_{taskShortId}/deploy-log.txt` | |
  | merge_commit_sha | string(40) | 否 | null | merge 到 master 的 commit |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 创建发布任务 | 用户填 deploy_port(平台检测冲突)+ **deploy_host(默认按 `{slug}.{deploy_base_domain}` 预填,可改,平台校验合法性与全平台唯一)** → 拉起容器 → checkout master → **merge req-{reqId}(容器内执行,但 merge commit 通过 GitLab API 用平台 bot token 创建,确保系统动作可追溯)** | deploying |
  | merge 冲突 | AI 自动解决(在容器内 merge + commit + push 用 bot token)→ 仍冲突 → failed,提示人工在终端介入 | |
  | 部署脚本执行 | 容器内运行,日志实时推送到工作台 | |
  | 健康检查 | `GET http://localhost:{port}/` 200(可配置路径)→ deployed | URL 可公开访问 |
  | **部署产物 commit** | CHANGELOG.md + deploy-log.txt commit 到 master 的 `docs/{doc_dir}/`(**用平台 bot token,系统动作**) | |
  | 部署失败 | status=failed → 可驳回回测试(新建 test 任务)或重试 | |
  | 需求下所有发布任务 deployed | 需求 → done → 触发 R7 归档 | |
  | **容器不销毁** | **部署中的任务容器保持运行**(对外提供服务),直到"下线"或"项目归档" | 持续运行 |
- **依赖**:R6、R4、R15
- **异常与边界场景**:
  - 端口冲突:平台检测 `deploy_port` 在**全平台**唯一,冲突拒绝
  - **deploy_host 冲突/非法**:全平台唯一(与端口同维度检测);自定义域名未解析到网关时健康检查可达但外网 404/超时——创建时提示"请先将域名 A 记录解析到 {网关地址}"(不阻塞创建,Q29)
  - 单项目**同时部署数 ≤ 5**
  - 部署中的任务**不占用** R4 的"并发 running 任务 ≤ 3"配额
  - 部署容器崩溃 → 告警到项目 owner **站内信 + 钉钉 webhook**(Q12 已确认)
  - 下线 = 用户点击"下线" → 摘除路由 + 销毁容器
- **验收标准**:
  1. 发布后 `http://{deploy_host}:{port}` 可公开访问(默认域名 + 自定义域名两种)
  2. deploy_host 自定义后 URL 随之变化;非法/重复 host 被拒绝
  3. 部署产物 commit 到 master
  4. 需求下所有发布完成后,需求自动 done 并触发归档
  5. 下线后 URL 立即不可访问

### R8:任务级容器(执行沙箱,Runner 架构)

- **描述**:**每个任务一个专属容器**,任务创建时由**某个 Runner** 拉起,任务结束销毁;容器内预装开发工具链与 Claude CLI。**容器可在不同的 Runner 机器上运行**(Runner 架构,见 R16)
- **触发场景**:任务创建时由调度器分配到某个 Runner 拉起
- **前置条件**:R4 任务已建;至少一个 Runner 在线(R16)
- **边界定义**:
  - 做什么:
    - 镜像 `platform/devbox:v1`(基于 `mcr.microsoft.com/devcontainer/universal:linux` + Claude CLI + 高频包预装,详见 ARCH D10)
    - 启动时 `git clone {gitlab_repo_url} /workspace/{path}`(用 R1 的用户 token,通过环境变量注入)+ `git checkout {base_branch}` + `git checkout -b {work_branch}`(若 ≠ base)
    - 端口约定:前端 dev server **5173**、后端服务 **8000**;Runner 上映射到**随机宿主机端口**(网关转发用)
    - 任务结束(成功/失败/取消/超时)**Runner 销毁容器**
    - **例外**:R7 发布任务 deployed 后容器**保持运行**(在**专用 deploy Runner** 上),直到用户下线
  - 不做什么:
    - **不做**自定义镜像(V1 统一镜像)
    - **不做** docker-compose 多容器
    - **不做** SSH 直连
    - **不做**宿主机挂载(V1 数据全走 GitLab,容器是纯计算资源)
    - **不做**内嵌 MySQL/Redis(若需要,引导用户在容器内自行 `apt install` 或 docker 多容器,V2 再议)
- **字段定义**:
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | container_id | string | 是 | - | Runner 上的 docker id |
  | task_id | ref(R4) | 是 | - | 唯一(部署中任务例外) |
  | runner_id | ref(R16) | 是 | - | **运行该容器的 Runner** |
  | status | enum | 是 | creating | creating/running/stopped/failed/destroyed |
  | image | string | 是 | `platform/devbox:v1` | |
  | cpu_limit / mem_limit / disk_limit | string | 是 | 2c / 4g / 10g | |
  | exposed_ports | json | 是 | [5173, 8000] | 容器内端口 |
  | runner_host_port_5173 | int | 否 | null | **Runner 上映射到 5173 的宿主机端口**(网关转发用) |
  | runner_host_port_8000 | int | 否 | null | **Runner 上映射到 8000 的宿主机端口** |
  | created_at / destroyed_at | datetime | - | - | |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 拉起 | 调度器选 Runner(最少负载)→ Runner 收到指令 → `docker run -p {随机}:5173 -p {随机}:8000 -e ...` + git clone + checkout → 上报容器 id 与端口映射到平台 | running |
  | 任务结束 | 销毁前**强制 push 未 push 的 commit** → Runner `docker stop + rm` | destroyed |
  | 崩溃 | Runner 自动 restart ≤ 3 次 → failed,任务标记 failed,Runner 清理 | destroyed |
  | 项目删除/归档 | 该项目所有容器 stop + rm(跨所有 Runner) | destroyed |
  | 部署中容器 | 任务 done 后容器**保留运行**在 **deploy Runner** 上,直到用户"下线"或"项目归档" | running |
  | Runner offline | Runner 上的容器**继续跑**(Runner 是薄代理),平台标记容器"Runner offline";Runner 恢复后重新上报状态 | - |
- **依赖**:R4、R16
- **异常与边界场景**:
  - 单用户**同时运行容器 ≤ 5**(含部署中)
  - 平台总容器数上限(平台配置,默认 50,跨所有 Runner)
  - git clone 失败(token 失效)→ 容器创建失败,引导重新绑定 R1
  - 容器销毁前 push 失败(GitLab 不可用)→ Runner 保留容器 30 分钟,平台重试 push;仍失败则告警 + 销毁(代码丢失)
  - **Runner 负载不均衡**:调度器每次选最少负载 Runner;若所有 Runner 负载相同,随机选
  - **部署任务固定在 deploy Runner**(R16 标记 `role=deploy` 的 Runner)
- **验收标准**:
  1. 任务创建后容器 30s 内在某个 Runner 上拉起
  2. 任务结束后容器被销毁
  3. 部署中的容器不被销毁,且在 deploy Runner 上
  4. 销毁前未 push 的 commit 被强制 push
  5. Runner offline 时容器继续跑,Runner 恢复后状态同步正确

### R9:Web 终端(实时 TTY)

- **描述**:任务容器内的实时交互终端,**Claude CLI 也跑在同一容器**,用户在终端可看到/介入 Claude;同时 Claude Agent SDK 的"工具调用事件"在工作台另一侧以结构化形式呈现
- **触发场景**:任务工作台 → 终端区(仅任务详情页可用)
- **前置条件**:R8 running
- **边界定义**:
  - 做什么:
    - xterm.js + WebSocket + docker exec pty
    - 多 Tab(独立 shell session)
    - **Claude CLI 模式**:用户可在终端里直接 `claude` 启动交互式会话
    - **Claude Agent SDK 模式**(任务执行主路径):平台后端跑 SDK,工具调用事件(读/写/执行/git)**结构化推送到工作台"活动流"**;关键命令同时回显到终端(只读,前缀 `[ai]` 高亮)
    - 滚动缓冲 5000 行
  - 不做什么:
    - **不做** SSH 直连
    - **不做**终端录制回放(V1)
    - **不做**无任务时的"项目级终端"(容器是任务级的)
- **字段定义**:
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | session_id | uuid | 是 | auto | 每个 Tab 一个 |
  | task_id | ref(R4) | 是 | - | |
  | container_id | ref(R8) | 是 | - | |
  | shell | string | 是 | /bin/bash | |
  | created_by | ref(R1) | 是 | - | |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 打开 Tab | docker exec 新 pty,cwd=/workspace | 可交互 |
  | 任务执行中 | SDK 工具事件流 → 活动流面板;关键命令(git commit、npm install)同时回显终端(只读) | 双通道可见 |
  | 用户在终端启动 `claude` | 进入 Claude CLI 交互,**与 SDK 会话相互独立** | 用户主导 |
  | 用户在终端 git 操作 | 允许,commit/push 都生效;可能造成与 AI 的冲突,平台不阻止 | |
  | 关闭 Tab | kill pty | |
- **依赖**:R8
- **异常与边界场景**:
  - 高频输出限流 > 1000 行/秒丢弃中间
  - 破坏性命令不拦截,但写审计日志
  - 用户在终端 `git reset --hard` 丢失 AI 未 commit 的修改 → 平台不兜底(用户负责)
- **验收标准**:
  1. 终端可正常交互
  2. 任务执行时,活动流与终端同时可见 Claude 行为
  3. 用户可在终端启动 Claude CLI 独立会话
  4. 用户可在终端执行 git 命令介入版本控制

### R10:实时预览(仅任务内)

- **描述**:任务容器内 5173/8000 端口的服务通过平台网关暴露为**项目成员可访问**的预览 URL,嵌入任务工作台 iframe
- **触发场景**:任务工作台 → 预览区(仅任务详情页可用)
- **前置条件**:R8 running;容器内有进程监听约定端口
- **边界定义**:
  - 做什么:
    - 端口探测:5173/8000 有监听 → 自动注册网关路由
    - URL 形态:`http://{slug}--{taskId}--{port}.{preview_base_domain}`(preview_base_domain 平台设置可配,Q28;HTTP,任务级唯一)
    - iframe 内嵌 + 新窗口打开
    - HMR WebSocket 透传
  - 不做什么:
    - **不做** HTTPS
    - **不做**自定义端口
    - **不做**预览公开访问(仅项目成员;公开访问走 R7)
    - **不做**无任务时的"项目级预览"
- **字段定义**:
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | port | int | 是 | - | 5173/8000 |
  | subdomain | string | 是 | `{slug}--{taskId}--{port}` | 任务级唯一 |
  | upstream | string | 是 | `http://{container_ip}:{port}` | |
  | status | enum | 是 | inactive | active/inactive |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 端口监听 | 注册路由 → active | 预览亮起 |
  | 端口关闭 | 摘除路由 → inactive | 显示"服务未启动" |
  | 访问预览 | 鉴权:登录 + 项目成员 | 非成员 403 |
  | 容器销毁 | 路由摘除 | URL 不可访问 |
  | iframe 加载失败 | 提示重试 + 新窗口 + 看终端日志 | |
- **依赖**:R8、R12(权限)
- **异常与边界场景**:
  - 端口被占但非 HTTP:健康检查失败 inactive
  - 泛域名证书 `*.{preview_base_domain}`(虽 HTTP only,但备未来升级)
- **验收标准**:
  1. 容器内起 5173 服务 ≤ 3s 预览可见
  2. 代码改动 HMR 自动刷新
  3. 非成员访问被拒
  4. 容器销毁后预览 URL 失效

### R11:在线代码编辑器(双模式)

- **描述**:基于 Monaco 的在线编辑器,**双模式**:
  - **任务内模式**(完整):读写任务容器内 `/workspace`,AI 修改实时刷新,提供**任务级 Diff 视图**
  - **项目模式**(只读):无任务时,从 **GitLab API** 拉文件展示,**只读不可编辑**
- **触发场景**:任务工作台 → 编辑器区(完整模式);项目主页 → 代码 Tab(只读模式)
- **前置条件**:任务模式 R8 running;只读模式 R2 GitLab token 有效
- **边界定义**:
  - 做什么:
    - **任务内模式**:
      - 文件树(增删改查/重命名/拖拽)
      - Monaco(语法高亮/查找替换/多光标/minimap)
      - 文件保存即写入容器(500ms 防抖)
      - **AI 修改实时刷新**(文件 watcher + 编辑器平滑更新)
      - **任务级 Diff 视图**:列出本任务 git diff 涉及文件,逐文件 diff,可"接受/拒绝"(拒绝=回滚该文件)
      - **文件树「全部 / 变更」双视图**(2026-09-21 Q27):变更视图列出本任务改动文件清单——**相对 `base_branch` 的全部差异**(已 commit + 未 commit,git 口径,不区分 AI/人),**按仓库分组**(主仓库 / test 仓库等),每文件标注变更类型(M/A/D/R)与行数(+X/-Y);面板徽标显示变更总数;**点击文件直达其 Diff 视图**(接受/拒绝操作在 Diff 视图完成)
    - **项目模式**:
      - 通过 GitLab API 浏览任意分支的文件树与文件内容
      - 只读,不可编辑;不可创建/删除/重命名
  - 不做什么:
    - **不做**多人实时协同(光标共享/CRDT)—— V1 假设任务**单执行者**,人审阅 AI 而非与人协同
    - **不做** LSP/智能补全/跳转定义
    - **不做** Git 可视化操作面板(stage/commit/push 走终端)
    - **不做**二进制预览(图片除外)
    - **不做**大文件编辑(> 2MB 只读)
    - **不做**变更清单按作者区分标注(git 无法可靠区分 AI/人;可在 commit 详情查元数据)
- **字段定义**:沿用文件树常规字段,无需持久化(任务模式读容器,项目模式读 GitLab API)
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 项目模式打开文件 | 调 GitLab API `GET /projects/:id/repository/files/:path?ref={branch}` → 显示 | 只读 |
  | 任务模式打开文件 | 从容器读 → 显示 | 可编辑 |
  | AI 修改了打开的文件 | watcher 触发 → 编辑器更新 + toast"AI 修改了此文件" | |
  | 用户编辑与 AI 修改冲突 | **以容器为准**,提示"AI 已修改,已为你重新加载" | |
  | 任务结束 → Diff 视图 | 列出本任务 git diff 文件,逐文件 accept/reject | reject = `git checkout HEAD@{task_start} -- {file}` |
  | 文件被外部删除 | 编辑器标记,可另存 | |
  | 切换「变更」视图 | 聚合容器内 git 数据(diff base...work + status)→ 按仓库分组展示改动清单,徽标计数 | 快速核查 |
  | 执行中 AI 修改文件(变更视图打开中) | 列表实时刷新(watcher/事件驱动),徽标 +1 | |
  | 点击变更文件 | 直达该文件 Diff 视图 | 接受/拒绝在 Diff 视图 |
  | 变更文件 > 500 | 列表虚拟滚动,提示"建议按仓库/目录聚焦" | 不截断 |
- **依赖**:R8(任务模式)/ R2(项目模式)
- **异常与边界场景**:
  - 多人打开同一文件:不冲突(各自编辑,后保存覆盖前者;V1 接受)
  - GitLab API 超时 → 显示"无法加载,请稍后重试"
  - 文件 watcher 失效 → 手动刷新按钮
- **验收标准**:
  1. 项目模式能从 GitLab API 浏览任意分支文件
  2. 任务模式 AI 修改的文件实时刷新可见
  3. Diff 视图能列出任务所有改动并可单独回滚
  4. 项目模式只读,任何写操作被禁
  5. 文件树变更视图列出本任务全部改动文件(类型 + 行数,按仓库分组),点击直达 Diff

### R12:项目成员与协作

- **描述**:项目级成员与三档角色权限
- **触发场景**:项目设置 → 成员 Tab
- **前置条件**:R2
- **边界定义**:
  - 做什么:邀请(**手机号搜索**)/移除/角色变更
  - 不做什么:组织层级/跨项目权限继承/审批流
- **字段定义**:
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | project_id | ref(R2) | 是 | - | |
  | user_id | ref(R1) | 是 | - | |
  | role | enum | 是 | viewer | owner/editor/viewer |
  | invited_by | ref(R1) | 是 | - | |
  | joined_at | datetime | 是 | now | |
- **交互规则**(权限矩阵):
  | 操作 | owner | editor | viewer |
  |---|---|---|---|
  | 查看项目/需求/任务/代码(只读)/预览/知识库 | ✅ | ✅ | ✅ |
  | 创建/编辑需求 | ✅ | ✅ | ❌ |
  | 知识库管理(建库/编辑空模板页面/目录导入/同步/删库) | ✅ | ✅ | ❌ |
  | 跨项目聚合视图(Dashboard/四维管理菜单,限成员项目) | ✅ | ✅ | ✅(仅查看) |
  | 启动需求打磨任务 | ✅(需绑定 token) | ✅(需绑定 token) | ❌ |
  | 评审需求(通过/驳回) | ✅(需绑定 token,通过时用其 token commit PRD) | ✅(同左) | ❌ |
  | 创建/执行任务(dev/test/release) | ✅(需绑定 token) | ✅(需绑定 token) | ❌ |
  | 用任务内终端/编辑器 | ✅ | ✅ | ❌ |
  | 邀请/移除/改角色 | ✅ | ❌ | ❌ |
  | 改模型配置(R13) | ✅ | ❌ | ❌ |
  | 改项目 GitLab 绑定(R2) | ✅ | ❌ | ❌ |
  | 归档/删除项目 | ✅ | ❌ | ❌ |
  | 知识条目提升到平台级(R14) | ✅ | ❌ | ❌ |
  | 转让 owner | ✅(降为 editor) | - | - |

  **"需绑定 token"**:执行该操作前,平台校验用户已绑定 GitLab token 且对该 repo 有 read+write 权限;未绑定则跳转个人设置页引导绑定(R1)。

  **超管特别规则**:超管在**所有项目**(含未参与)自动等同 owner 权限(R19);操作时审计日志记录其 superadmin 身份。
- **依赖**:R1、R2
- **异常与边界场景**:
  - 项目必须 ≥1 owner
  - 单项目成员 ≤ 50
- **验收标准**:
  1. 权限矩阵每条可验证
  2. viewer 写操作前后端双重拦截

### R13:模型接入(项目级 url+key)

- **描述**:每个项目配置一组 OpenAI 兼容 LLM endpoint,任务执行与 AI 辅助使用;支持会话级临时切换
- **触发场景**:项目设置 → 模型 Tab / 首次建任务未配置时引导
- **前置条件**:R2
- **边界定义**:
  - 做什么:项目级 url+key+model,多组配置(主/备),连接性测试,会话级覆盖
  - 不做什么:平台统一计费/key 池/模型路由
- **字段定义**:
  | 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
  |---|---|---|---|---|---|
  | config_id | uuid | 是 | auto | - | |
  | project_id | ref(R2) | 是 | - | - | |
  | name | string(64) | 是 | - | 同项目唯一 | |
  | base_url | string(255) | 是 | - | http/https | OpenAI 兼容 |
  | api_key | string(255) | 是 | - | AES-GCM 加密存储 | 接口永不回显完整 |
  | model | string(64) | 是 | - | - | claude-sonnet-5 / gpt-5 / deepseek-chat 等 |
  | is_default | bool | 是 | false | 同项目最多一个 | |
  | enabled | bool | 是 | true | - | |
  | created_by | ref(R1) | 是 | - | | |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 保存 | `GET {base_url}/models` 连通性测试,失败拒绝 | 提示错误 |
  | 任务执行 | 默认 default 配置;启动任务时可临时切换(会话级) | 当次生效 |
  | key 展示 | 前 4 + 后 4,中间 *** | |
  | 删 default | 拒绝,先指定新 default | |
  | **SDK 模式** | 平台后端用配置调 LLM(主路径) | |
  | **CLI 模式** | 平台把配置注入容器 env(`ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` 或对应变量) | Claude CLI 用 |
- **依赖**:R2
- **异常与边界场景**:
  - 容器内 env 注入的 key **仅容器内存**,不落容器镜像/日志
  - 未配置时,任务/AI 辅助入口禁用并引导
  - **2026-09-23 增量3**:未配置判定修订为「项目级与平台级**均**未配置才禁用」;项目未配置时回退平台默认 LLM(见 R23 / Q30–Q32)
- **验收标准**:
  1. 至少能配置 Claude/OpenAI/DeepSeek 任意兼容 endpoint 跑通任务
  2. key 不明文出现在接口/日志/前端
  3. SDK 与 CLI 两种模式都能用同一组配置

### R14:归档与知识库

- **描述**:需求 done 后,自动整理全流程产物生成归档页;同时 AI 提取**可复用知识**进知识库(条目级;文档空间形态的「项目知识库」见 R20,两者并存)
- **触发场景**:需求 status=done 自动触发 / 用户手动点击"归档"
- **前置条件**:R7 deployed
- **边界定义**:
  - 做什么:
    - 归档页:时间线视图,展示从需求到发布的全过程关键节点(数据来自 GitLab commit + 任务历史 + 部署记录)
    - AI 生成**归档总结** `docs/{YYYYMMDD}_{descSlug}_archive/summary.md`,**commit 到 master**(此时需求分支已 merge;日期为归档当天,系统生成无任务)
    - AI 提取**知识条目**:可复用代码片段 / 通用模式 / 工具用法,入库
    - 知识库**项目内 + 平台级**两级,支持搜索
  - 不做什么:
    - **不做**知识条目版本管理
    - **不做**知识条目权限细分(V1 项目内成员可见项目库,平台库全员可见)
    - **不做**知识推荐(仅搜索)
- **字段定义**(KnowledgeEntry):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | entry_id | uuid | 是 | auto | |
  | project_id | ref(R2) | 否 | null | null=平台级 |
  | req_id | ref(R3) | 是 | - | 来源需求 |
  | type | enum | 是 | - | code_snippet / pattern / pitfall / doc |
  | title | string(128) | 是 | - | |
  | content | text | 是 | - | Markdown |
  | tags | json | 否 | [] | 字符串数组 |
  | source_links | json | 否 | [] | 关联 commit/任务/部署 URL |
  | created_by | enum | 是 | ai | ai / human |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 需求 done | 自动生成归档页 + AI 起草总结 commit 到 master `docs/{YYYYMMDD}_{descSlug}_archive/summary.md` | 项目成员可编辑(通过新任务) |
  | AI 提取知识 | 默认进**项目级**知识库;owner 可"提升到平台级" | |
  | 用户手动新增知识 | 项目内任意成员可建 | |
  | 搜索 | 全文 + tag 过滤,项目内 / 平台级 Tab 切换 | |
- **依赖**:R7、R13
- **异常与边界场景**:
  - AI 提取的知识默认 **draft 状态**,人审后才 publish
  - 归档后需求不可再打开任务(只读)
  - 归档总结需修改 → 创建一个新的 dev 任务专门改文档
- **验收标准**:
  1. 需求 done 后归档页可见,summary.md 已 commit 到 master
  2. 知识库可搜索到归档的条目
  3. 平台级知识需 owner 提升

### R15:平台网关与域名(支持 Runner 代理)

- **描述**:承载预览(R10)与部署(R7)的统一反向代理,基于泛域名 + 端口;**Runner 架构下,网关直连 Runner 宿主机映射端口(2026-09-21 D20 修订:已取消 Runner 本地代理层)**
- **触发场景**:任何预览/部署 URL 访问
- **前置条件**:平台部署时配置
- **边界定义**:
  - 做什么:
    - 预览泛域名 `*.{preview_base_domain}`(preview_base_domain **平台设置可配**,Q28,默认示例 `preview.coding-console.zhanqitv.com.cn`;预览,任务级)
    - 部署域名 `{deploy_host}:{port}`(deploy_host 默认 `{slug}.{deploy_base_domain}`,deploy_base_domain 平台设置可配;**发布任务可自定义 deploy_host,Q29**)
    - 动态路由注册/摘除(容器端口监听驱动 / 部署事件驱动)
    - **路由 upstream 直连 Runner 宿主机映射端口**:`http://{runner_host}:{runner_mapped_port}`(D20 取消本地代理,无 Runner 层 Nginx)
    - 预览路由**鉴权**,部署路由**公开**
    - WebSocket 透传(HMR/TTY)
    - 流量/访问日志
  - 不做什么(V1):
    - **不做** HTTPS(HTTP only)
    - **不做** CDN
    - **不做** WAF/防火墙(V1 信任内网/基础防护即可)
    - **不做**自定义域名
- **字段定义**(Route):
  | 字段 | 类型 | 必填 | 说明 |
  |---|---|---|---|
  | route_id | uuid | 是 | |
  | host | string | 是 | 完整 host(含端口) |
  | upstream | string | 是 | **`http://{runner_host}:{runner_mapped_port}`**(Runner 宿主机映射端口直连;D20 已取消本地代理) |
  | type | enum | 是 | preview / deploy |
  | project_id | ref(R2) | 是 | |
  | task_id | ref(R4) | 否 | preview 必填 |
  | container_id | ref(R8) | 是 | |
  | runner_id | ref(R16) | 是 | |
  | auth_required | bool | 是 | preview=true, deploy=false |
  | status | enum | 是 | active/inactive |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 注册路由 | 端口监听/部署事件触发 → 平台查询容器的 `runner_id` + `runner_host_port_*` → 拼接 upstream → 注册到网关 | active |
  | 摘除 | 端口关闭/容器销毁/下线 | inactive |
  | 访问 preview | 校验 JWT + 项目成员 → 转发到 Runner 宿主机映射端口(直达容器) | 非成员 403 |
  | 访问 deploy | 公开 → 转发到 deploy Runner 宿主机映射端口(直达容器) | |
  | 端口冲突 | deploy_port 全平台唯一,冲突拒绝 | |
  | **Runner offline** | 路由保留,但 upstream 不可达 → 网关返回 502 + "Runner offline" 提示 | |
- **依赖**:R8、R16
- **异常与边界场景**:
  - 上游 5xx → 502 页面带项目名与日志链接
  - 单 host QPS 上限(防爬/防滥用,默认 100)
  - 端口池 `10000-10099`(100 个端口,够 20 个项目 × 5 个部署)
  - **Runner 宿主机端口冲突**:Runner 启动容器时分配随机宿主机端口(范围 20000-29999),冲突自动重试
- **验收标准**:
  1. 预览鉴权正确,部署公开
  2. WebSocket 透传正常(HMR/TTY)
  3. 端口冲突被拒绝
  4. 容器销毁后路由自动摘除
  5. Runner offline 时路由保留但返回 502 + 明确提示
  6. 路由 upstream 正确指向 Runner 宿主机映射端口

### R16:Runner 管理(分布式容器执行)

- **描述**:Runner 是**容器执行的代理节点**,部署在不同的机器上;Runner 主动连接平台(WebSocket),接收任务指令(启动/停止容器),本地通过 Docker SDK 管理容器,并把容器状态/日志/事件回传平台
- **触发场景**:**仅超管**在"平台设置 → Runner 管理"页生成 Runner token(R19)/ 运维在某台机器上启动 Runner 容器;**Runner 管理页仅超管可见可操作**,普通用户无入口、调 API 返回 403
- **前置条件**:平台已部署;Runner 机器已装 Docker
- **边界定义**:
  - 做什么:
    - **Runner 注册**:运维在某台机器上 `docker run -e PLATFORM_URL=... -e RUNNER_TOKEN=... platform/runner:v1` → Runner 启动后**主动 WebSocket 连接平台** → 平台校验 token → 注册上线
    - **任务调度**:平台后端调度器根据"最少负载"策略选择 Runner(部署任务固定在 `role=deploy` 的 Runner)
    - **容器管理**:平台通过 WebSocket 向 Runner 发送指令(启动/停止/销毁/exec);Runner 本地调 Docker SDK 执行,并回报结果
    - **心跳保活**:Runner 每 30s 向平台发心跳;60s 无心跳平台标记 Runner offline
    - **状态回传**:Runner 监听本地容器事件(start/die/OOM 等),实时回传平台
    - **端口映射回报**:Runner 启动容器时分配随机宿主机端口,回报给平台(网关转发用)
    - **端口映射回报**(2026-09-21 D20 修订):Runner 启动容器时分配随机宿主机端口并直接回报平台,平台网关直连该端口;**不再有 Runner 本地代理层**
    - **Runner 角色**:`worker`(默认,跑任务容器)/ `deploy`(专用跑部署容器,需绑定公网 IP/域名)
  - 不做什么:
    - **不做** Runner 自动扩缩容(V1 手动增减 Runner)
    - **不做** Runner 上的容器迁移(Runner 掉线,容器继续跑;任务不迁移到其他 Runner)
    - **不做** Runner 标签匹配(V1 只区分 worker/deploy;V2 再加 GPU/大内存等标签)
    - **不做** Kubernetes(Runner 就是"装了 Docker 的机器",V1 不上 K8s)
- **字段定义**(Runner):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | runner_id | uuid | 是 | auto | |
  | name | string(64) | 是 | - | 运维起的名字(如 "runner-beijing-01") |
  | role | enum | 是 | worker | worker / deploy |
  | token_hash | string | 是 | - | Runner token 的 bcrypt hash(平台不存明文) |
  | status | enum | 是 | offline | online / offline / disabled |
  | last_heartbeat_at | datetime | 否 | null | |
  | machine_info | json | 否 | null | `{os, arch, cpu_count, mem_total_gb, docker_version}` |
  | current_containers | int | 是 | 0 | 当前运行的容器数(调度用) |
  | max_containers | int | 是 | 10 | 该 Runner 最多跑多少容器 |
  | public_ip | string(64) | 否 | null | deploy Runner 必填(部署 URL 指向该 IP) |
  | created_by | ref(R1) | 是 | - | 创建 token 的超管 |
  | created_at | datetime | 是 | now | |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 超管生成 Runner token | 平台设置 → Runner 管理 → "新建 Runner" → 填 name + role → 生成一次性 token(仅显示一次) | 运维复制 token |
  | Runner 启动 | `docker run -e PLATFORM_URL=wss://platform.example.com/ws/runner -e RUNNER_TOKEN=xxx platform/runner:v1` → 连接平台 → 平台校验 token_hash → 标记 online | Runner 列表显示 online |
  | 心跳 | Runner 每 30s 发 `ping`;平台 60s 未收到 → 标记 offline | Runner 列表灰显 |
  | 任务调度 | 平台选 `status=online AND current_containers < max_containers AND role 匹配` 的 Runner 中 `current_containers` 最少的 | 任务分配到该 Runner |
  | Runner 上的容器事件 | Runner 监听 docker events → start/die/OOM → 实时回传平台 → 平台更新容器状态 | 前端可见 |
  | Runner 下线(运维主动) | Runner 收到 SIGTERM → 通知平台 → 平台标记 offline → Runner 上的 running 容器**不动**(继续跑) | Runner 列表灰显 |
  | Runner 恢复 | Runner 重新连接 → 上报本地实际运行的容器列表 → 平台对账(数据库 vs 实际) | 状态一致 |
  | 部署任务调度 | 仅选 `role=deploy AND online` 的 Runner;多个 deploy Runner 时选最少负载 | 部署固定在 deploy Runner |
  | Runner token 泄露 | 超管在 Runner 管理页"重置 token" → 旧 token 失效,Runner 需用新 token 重启 | 安全 |
- **依赖**:R1(超管)、R8
- **异常与边界场景**:
  - **Runner offline 时其上的容器**:继续跑(Runner 是薄代理,容器独立于 Runner 进程);平台标记容器"Runner offline",**WebSocket 终端/预览不可用**(网关无法转发);Runner 恢复后恢复
  - **Runner 全部 offline**:任务创建时**排队**,前端显示"等待可用 Runner";超管告警
  - **Runner 上 Docker daemon 挂了**:Runner 上报 "docker daemon unavailable" → 平台标记 Runner failed,不再调度
  - **Runner 时钟漂移**:心跳带时间戳,平台校验时钟差 > 5min 拒绝(避免 token 重放)
  - **Runner 与平台时钟不同步导致的心跳误判**:平台容忍 ±30s 时钟差
  - **2026-09-23 增量3**:Runner 管理页新增宿主机终端排障入口(见 R26 / Q37–Q38)
- **验收标准**:
  1. 运维能用 token 在某台机器上启动 Runner 并注册到平台
  2. 任务能分配到 Runner 并在其上拉起容器
  3. Runner offline 时任务排队,Runner 恢复后继续
  4. Runner 上的容器事件(start/die)能实时回传平台
  5. 部署任务固定在 deploy Runner 上
  6. Runner token 重置后旧 token 失效

### R17:MCP server 与 Skills 管理

- **描述**:平台预装常用 MCP server 与 Skills 到任务容器镜像;**项目级 MCP server 配置**与**Skills** 允许用户自定义;AI 在任务中可使用 MCP server 扩展工具能力,使用 Skills 扩展方法论
- **触发场景**:任务创建时自动注入 / 项目设置 → MCP/Skills Tab 管理
- **前置条件**:R2(项目已建)
- **边界定义**:
  - 做什么:
    - **镜像预装**(platform/devbox:v1):
      - 常用 MCP server(filesystem / git / github / sqlite / brave-search)
      - 常用 Skills(平台官方维护,如"代码审查"、"写测试"、"重构")
    - **项目级 MCP server 配置**:
      - 项目设置里允许用户**编辑 JSON 配置**(沿用 Claude Code 原生格式)
      - 提供**常用 MCP server 模板**(PostgreSQL / Redis / GitHub / Slack 等),用户填参数即可
      - 配置里可能包含敏感信息(数据库密码/API key),**AES-256-GCM 加密存储**(与 R13 一致)
    - **Skills 管理**:
      - **平台级 Skills**:平台官方维护,所有项目可用;超管在"平台设置 → Skills 市场"维护
      - **项目级 Skills**:项目成员在项目设置里**上传自己的 `.md` 文件** 或 **从平台级 Skills 市场选择安装**
      - Skills 内容格式沿用 **Claude Code Skills 原生格式**(YAML frontmatter + Markdown 正文)
    - **任务创建时注入**:
      - 平台把项目级 `mcp_config` 注入到容器 `~/.claude/config.json`(与镜像预装的 MCP server **合并**,项目级覆盖同名)
      - 平台把项目级 Skills 列表对应的 `.md` 文件写入容器 `~/.claude/skills/` 目录(与镜像预装的 Skills **合并**,项目级覆盖同名)
  - 不做什么:
    - **不做**用户级 Skills(跟随用户跨项目;V1 太细)
    - **不做** Skills 社区市场(用户分享 Skills;V2 再做)
    - **不做**远程 MCP server(有状态/资源密集/跨任务共享;V2 再做)
    - **不做** Skills 版本管理(V1 覆盖式更新)
- **字段定义**(Skill 表):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | skill_id | uuid | 是 | auto | |
  | name | string(64) | 是 | - | 全局唯一(kebab-case) |
  | description | string(255) | 是 | - | 一句话描述 |
  | content | text | 是 | - | Markdown 正文(YAML frontmatter + 正文) |
  | scope | enum | 是 | platform | platform(平台级)/ project(项目级) |
  | project_id | ref(R2) | 否 | null | scope=project 时必填 |
  | created_by | ref(R1) | 是 | - | |
  | created_at / updated_at | datetime | 是 | now | |

  **字段定义**(ProjectSkill 关联表):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | project_id | ref(R2) | 是 | - | |
  | skill_id | ref(Skill) | 是 | - | |
  | installed_by | ref(R1) | 是 | - | |
  | installed_at | datetime | 是 | now | |

  **字段定义**(Project 表新增):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | mcp_config_encrypted | text | 否 | null | 项目级 MCP server 配置(JSON),AES-256-GCM 加密 |

- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 项目设置 → MCP Tab → 编辑配置 | 用户编辑 JSON → 平台校验 JSON 格式合法 → **AES-256-GCM 加密**存到 `mcp_config_encrypted` | 保存成功 |
  | 项目设置 → MCP Tab → 用模板 | 用户选模板(如 PostgreSQL)→ 填参数(host/port/user/password)→ 平台生成 JSON → 加密存储 | 保存成功 |
  | 项目设置 → Skills Tab → 从市场安装 | 列出平台级 Skills(scope=platform)→ 用户点击"安装" → 写入 `project_skills` 关联表 | 安装成功 |
  | 项目设置 → Skills Tab → 上传自定义 Skill | 用户上传 `.md` 文件 → 平台校验格式(YAML frontmatter 必须有 name/description)→ 写入 `skills` 表(scope=project)+ `project_skills` 关联表 | 上传成功 |
  | 项目设置 → Skills Tab → 卸载 | 删除 `project_skills` 关联记录 | 卸载成功 |
  | 任务创建时注入 | 平台读 `mcp_config_encrypted` 解密 + 读 `project_skills` 关联的 Skills 内容 → 注入到容器 `~/.claude/config.json` 与 `~/.claude/skills/*.md` | AI 可用 |
  | 镜像预装 vs 项目级覆盖 | 同名 MCP server / Skill,**项目级覆盖镜像预装** | |
  | 敏感信息 | MCP 配置里的密码/key 在**接口返回时打码**(前 4 位 + 后 4 位,中间 ***);**容器内 env 注入时解密** | 前端不明文 |
- **依赖**:R2
- **异常与边界场景**:
  - **MCP 配置 JSON 格式错误**:保存时拒绝,提示具体错误行
  - **Skill `.md` 文件格式错误**(缺 YAML frontmatter / name / description):上传时拒绝,提示具体错误
  - **Skill name 冲突**(同名 platform Skill 与 project Skill):项目级覆盖平台级
  - **MCP server 启动失败**(如数据库连不上):Claude CLI 启动时会报错,任务失败,日志可见
  - **Skill 内容包含恶意指令**(如"删除所有文件"):V1 **不拦截**(用户自己负责);V2 可加内容审核
- **验收标准**:
  1. 镜像预装的 MCP server(filesystem/git)在所有任务容器中可用
  2. 项目级 MCP 配置(JSON)能保存并在任务中生效
  3. 项目级 Skills 能上传/安装/卸载,并在任务中生效
  4. 同名 MCP server / Skill 项目级覆盖镜像预装
  5. MCP 配置里的敏感信息加密存储,接口返回打码

### R18:站内信与通知

- **描述**:平台统一通知中心,承载所有告警/事件通知;**站内信 + 钉钉 webhook** 双通道;**实时 WebSocket 推送** toast
- **触发场景**:任务失败/部署崩溃/评审通过/被邀请加入项目等事件发生时自动触发
- **前置条件**:R1(用户);R2(项目)
- **边界定义**:
  - 做什么:
    - **站内信中心**:列表 + 详情 + 已读/未读/删除 + 分类 Tab(全部/告警/任务/项目)
    - **钉钉 webhook**:个人级(用户绑定自己的 webhook)+ 项目级(owner 绑定项目钉钉群 webhook)
    - **实时推送**:通知到达时,前端**实时弹 toast**(走 D5 统一 WebSocket 网关,频道 `/ws/notifications`)
    - **通知分级**:critical(紧急)/ normal(普通)/ info(信息),不同级别走不同通道
  - 不做什么:
    - **不做**邮件通知(仅站内信 + 钉钉)
    - **不做**通知模板自定义(V1 内置模板)
    - **不做**通知订阅规则自定义(V1 内置接收人规则)
- **字段定义**(Notification):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | notification_id | uuid | 是 | auto | |
  | recipient_id | ref(R1) | 是 | - | 接收人 |
  | type | enum | 是 | - | deploy_failed / runner_offline / task_failed / push_failed / review_approved / review_rejected / invited_to_project / task_done / deployed |
  | level | enum | 是 | normal | critical / normal / info |
  | title | string(255) | 是 | - | |
  | content | text | 是 | - | Markdown |
  | link | string(255) | 否 | null | 跳转链接(如任务详情页) |
  | project_id | ref(R2) | 否 | null | 关联项目(可空) |
  | task_id | ref(R4) | 否 | null | 关联任务(可空) |
  | read_at | datetime | 否 | null | 已读时间(null=未读) |
  | created_at | datetime | 是 | now | |

  **字段定义**(UserNotificationSettings,个人通知设置):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | user_id | ref(R1) | 是 | - | 唯一 |
  | dingtalk_webhook | string(255) | 否 | null | 个人钉钉 webhook URL(明文,非敏感) |
  | dingtalk_enabled | bool | 是 | false | 是否启用钉钉通知 |
  | realtime_toast_enabled | bool | 是 | true | 是否启用实时 toast |

  **字段定义**(Project 表新增):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | dingtalk_webhook | string(255) | 否 | null | 项目钉钉群 webhook URL(owner 配置) |
  | dingtalk_enabled | bool | 是 | false | 是否启用项目钉钉通知 |

- **交互规则**(通知级别 × 通道矩阵):
  | 级别 | 站内信 | 钉钉(个人) | 钉钉(项目) | 实时 toast |
  |---|---|---|---|---|
  | critical | ✅ | ✅(若启用) | ✅(若启用) | ✅(若启用) |
  | normal | ✅ | ❌ | ❌ | ✅(若启用) |
  | info | ✅ | ❌ | ❌ | ❌ |

  **通知场景与接收人**:
  | 场景 | type | level | 接收人 | 通道 |
  |---|---|---|---|---|
  | 部署容器崩溃 | deploy_failed | critical | 项目 owner + 部署操作人 | 站内信 + 钉钉(个人+项目) + toast |
  | Runner 全部 offline | runner_offline | critical | 超管 | 站内信 + 钉钉(个人) + toast |
  | 任务 failed(GitLab token 失效等) | task_failed | normal | 任务创建者 | 站内信 + toast |
  | 容器销毁前 push 失败 | push_failed | critical | 任务创建者 | 站内信 + 钉钉(个人) + toast |
  | 需求评审通过 | review_approved | normal | 需求创建者 | 站内信 + toast |
  | 需求评审驳回 | review_rejected | normal | 需求创建者 | 站内信 + toast |
  | 被邀请加入项目 | invited_to_project | normal | 被邀请人 | 站内信 + toast |
  | 任务完成 | task_done | info | 任务创建者 | 站内信 |
  | 部署成功 | deployed | info | 项目 owner + 部署操作人 | 站内信 |

- **依赖**:R1、R2、R4
- **异常与边界场景**:
  - **钉钉 webhook 失效**(调用返回 4xx):记录失败日志,不影响站内信;连续失败 3 次标记 webhook 失效,通知用户重新配置
  - **实时 toast 关闭时**:仅写站内信,不弹 toast
  - **用户离线时**:站内信正常入库,用户下次上线时看到未读计数
- **验收标准**:
  1. 部署崩溃时,项目 owner + 部署操作人收到站内信 + 钉钉 + toast
  2. 任务失败时,任务创建者收到站内信 + toast
  3. 用户能在"通知中心"查看历史通知,标记已读/删除
  4. 用户能在"个人设置 → 通知设置"绑定钉钉 webhook
  5. 项目 owner 能在项目设置绑定项目钉钉群 webhook
  6. 钉钉 webhook 失效时,连续失败 3 次后通知用户重新配置

### R19:平台角色与权限体系

- **描述**:平台采用**两级角色叠加**模型——平台级(User.role:superadmin / user)+ 项目级(ProjectMember.role:owner / editor / viewer,见 R12)。平台管理功能(平台设置 / **Runner 管理** / 用户管理 / 审计日志 / 平台级 Skills)**仅超管可用**;超管在**所有项目**中自动等同 owner
- **触发场景**:平台管理入口(用户中心)/ 任何受权限控制的操作 / 普通用户误访问管理功能
- **前置条件**:R1(账号)
- **边界定义**:
  - 做什么:
    - User 表新增 `role` 字段(superadmin / user,默认 user);超管可多人(Q4)
    - 平台级权限矩阵(见下);权限规则**代码固化**,不做动态配置
    - 超管 = 普通用户全部能力 + 平台管理能力(叠加,非互斥;超管可正常创建/参与项目)
    - **超管在所有项目(含未参与)自动等同 owner**(Q15):可查看、编辑需求、创建任务、评审、改配置、邀请/移除成员、归档/删除项目;审计日志记录其 superadmin 身份
    - **用户管理页**(仅超管):用户列表 / 禁用 / 启用;**禁用即全失效**(Q16):登录被拒 + 现有 JWT 立即失效 + 进行中任务立即取消(销毁前强制 push)
    - **审计日志查询页**(仅超管,Q17):按时间 / 用户 / 操作类型过滤;日志只读追加、不可删改
    - 平台注册邀请(超管)与项目成员邀请(owner,R12)分离:超管邀请新用户注册,项目 owner 邀请已有用户进项目
  - 不做什么:
    - 不做平台角色细分(仅 superadmin / user 两档)
    - 不做权限点动态配置(矩阵固化在代码)
    - 不做组织/团队层级
    - 不做超管操作的项目级审批流
- **平台级权限矩阵**:
  | 功能 | 超管 | 普通用户 | 归属 |
  |---|---|---|---|
  | 平台设置(GitLab 地址 / bot token / webhook secret / 全局参数如容器数上限) | ✅ | ❌(未配置时项目创建入口禁用并引导超管) | R2 / R8 |
  | **Runner 管理(新建 / 生成 token / 列表 / 禁用 / 启用 / 重置 token / 删除)** | ✅ | ❌(仅任务排队时看到"等待可用 Runner"提示) | R16 |
  | 用户管理(列表 / 禁用 / 启用) | ✅ | ❌ | R1 |
  | 平台注册邀请 | ✅ | ❌ | Q5 |
  | 平台级 Skills 市场维护(增删改) | ✅ | ❌(项目成员可安装 / 上传项目级 Skills) | R17 |
  | 审计日志查询 | ✅ | ❌ | R19 |
  | 平台告警接收(Runner 全部 offline 等 critical) | ✅ | ❌ | R18 |
  | 个人资料 / GitLab token 绑定 / 通知设置 | ✅ | ✅ | R1 / R18 |
  | 平台级知识库 | ✅ | ✅(只读) | R14 |
  | 创建项目 | ✅ | ✅ | R2 |
  | 任意项目的全部 owner 权限 | ✅(自动) | ❌(按项目角色,见 R12) | R12 |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 普通用户访问平台管理功能 | 前端隐藏入口;直接调 API 返回 403(前后端双重拦截) | 拦截 |
  | 超管禁用用户 | status=disabled → 现有 JWT 立即失效 → 该用户 running 任务立即取消(销毁前强制 push) | 用户被踢出 |
  | 超管启用用户 | status=active → 可重新登录 | 恢复访问 |
  | 超管操作任意项目 | 按 R12 owner 权限矩阵执行;审计日志记录操作者 superadmin 身份 | |
  | 超管重置/新建 Runner token | 沿用 R16 规则 | 旧 token 失效 |
  | 超管访问审计日志页 | 按时间 / 用户 / 操作类型过滤,分页查询 | 只读 |
- **依赖**:R1、R2、R12、R16、R17、R18
- **异常与边界场景**:
  - **最后一个超管不可被禁用/降级**(平台必须 ≥1 个超管)
  - 禁用用户时,其在 GitLab 上的 repo 成员资格**不同步移除**(V1);若需彻底收回 GitLab 权限,超管先将其移出项目(R2 会同步移除 GitLab 成员资格)
  - 禁用用户是某项目唯一 owner:项目保留,其他成员可继续工作;owner 空缺由超管代管(其本身等同 owner)或转让
  - 禁用用户已提交的 commit 历史保留(Git 天然特性)
  - 超管之间的操作(如超管 A 禁用超管 B)允许,受"最后一个超管"保护约束
  - 审计日志写入失败不阻塞业务操作(异步写 + 重试;连续失败进告警)
  - **2026-09-23 增量3**:审计事件全量接入清单落地(见 R25 / Q35–Q36)
- **验收标准**:
  1. 普通用户访问任何平台管理 API 返回 403,前端无入口
  2. **仅超管可见并操作 Runner 管理页**(新建 / 禁用 / 重置 token / 删除)
  3. 超管进入任意项目(含未参与)拥有 owner 全部权限,且审计记录 superadmin 身份
  4. 禁用用户后:登录被拒、现有会话立即失效、进行中任务立即取消
  5. 最后一个超管不可被禁用
  6. 审计日志可按时间 / 用户 / 类型过滤,记录不可删改
  7. 权限校验前后端双重拦截

### R20:项目知识库管理

- **描述**:项目级**文档空间**形态的知识库(wiki 形态),与 R14 知识条目**并存**。两种创建方式:**a) 空模板**(平台内可编辑,存平台数据库);**b) 目录导入**(读取项目绑定仓库的多个目录下 .md 文件生成快照,**平台内只读** + 手动同步)。查看统一用 **Markdown 渲染组件**,左侧**树形目录**导航
- **触发场景**:项目内 → 知识库 Tab → 新建知识库 / 浏览查看
- **前置条件**:R2(项目已建;导入型需项目已绑定仓库);R12(权限);R19(超管等同 owner)
- **边界定义**:
  - 做什么:
    - 知识库 CRUD(单项目可建多个知识库)
    - **空模板类型**:创建空白知识库 → 树形目录中新增/编辑/删除/拖拽排序页面;Markdown 编辑器(复用 R11 Monaco)+ 预览;内容存**平台数据库**
    - **目录导入类型**:选仓库(项目已绑定的任一 repo)→ 选分支(默认项目默认分支)→ 选择**多个目录**(GitLab API 目录树浏览多选,或手动输入路径)→ 平台用 **bot token** 调 GitLab API 拉取目录下全部 .md 文件(**保留目录层级**)→ 生成树形页面快照入库
    - **导入型只读**:仅可查看/搜索;提供"重新导入(同步)"按钮,按原 source_config 重新拉取并覆盖
    - 查看:左侧树形目录(可折叠/搜索定位)+ 右侧 Markdown 渲染(代码高亮);知识库内**标题 + 全文搜索**
    - 导入为**后台任务**,前端显示进度,完成后通知(R18 站内信 + toast)
  - 不做什么:
    - **不做**导入型的平台内编辑 / 回写 repo(修改仓库文件后走"重新导入"刷新)
    - **不做**自动定时同步(仅手动)
    - **不做**平台级知识库空间(V1 仅项目级;平台级仍只有 R14 知识条目)
    - **不做**页面级权限 / 分享链接 / 评论
    - **不做**非 .md 文件导入(图片等资源不导入,渲染时相对路径资源标注失效)
    - **不做**页面版本历史 / 回收站 / 导出 PDF(与 R14"不做版本管理"原则一致)
    - **不做**修改 source_config(换目录/分支需删库重建)
- **字段定义**(KnowledgeBase):
  | 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
  |---|---|---|---|---|---|
  | kb_id | uuid | 是 | auto | - | |
  | project_id | ref(R2) | 是 | - | - | |
  | name | string(64) | 是 | - | 同项目唯一 | 显示名 |
  | description | string(255) | 否 | "" | - | |
  | source_type | enum | 是 | blank | blank / repo_import | 空模板 / 目录导入 |
  | source_config | json | 否 | null | repo_import 必填 | `{repo_id, branch, paths: string[]}` |
  | last_synced_at | datetime | 否 | null | repo_import 有值 | 最近导入/同步时间 |
  | created_by | ref(R1) | 是 | - | - | |
  | created_at / updated_at | datetime | 是 | now | - | |

  **字段定义**(KnowledgeDoc,知识库页面):
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | doc_id | uuid | 是 | auto | |
  | kb_id | ref(R20) | 是 | - | 所属知识库 |
  | title | string(128) | 是 | 导入时取文件名 | |
  | path | string(255) | 是 | - | 树形路径,同库内唯一(如 `guide/intro`) |
  | content | text | 是 | "" | Markdown 正文 |
  | sort_order | int | 是 | 0 | 同级排序(拖拽) |
  | source_file_path | string(255) | 否 | null | 导入来源 repo 内完整路径;空模板为 null |
  | created_by / updated_by | ref(R1) | 是 | - | |
  | created_at / updated_at | datetime | 是 | now | |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 创建空模板 | 填 name/description → 生成空知识库(无页面)→ 引导"新建页面" | 进入知识库 |
  | 创建导入型 | 选仓库 → 选分支 → 多选目录 → 后台拉取 .md 生成树形快照 | 导入完成通知 |
  | 导入目录不存在/无 .md | 该路径跳过并提示;全部为空则导入失败 | 停留创建页 |
  | 查看页面 | 左树 + 右侧 Markdown 渲染(代码高亮) | |
  | 编辑页面(blank) | owner/editor 可增删改/拖拽排序;Monaco 编辑 + 预览;后保存覆盖前者 | 存平台库 |
  | 编辑页面(repo_import) | **只读**,编辑入口隐藏,API 写操作 403(前后端双重拦截) | 拦截 |
  | 重新导入(同步) | 按 source_config 重新拉取覆盖平台内容 → 更新 last_synced_at | 内容刷新 |
  | 同步时仓库/分支/目录已删 | 同步失败并提示具体原因;**保留上次快照** | 内容不变 |
  | 仓库已解绑(R2) | 快照保留可看;同步失败提示 | |
  | 搜索 | 库内标题 + 全文搜索,定位到页面 | |
  | 删除知识库 | owner/editor 二次确认;导入型删除**不影响 repo** | 列表移除 |
- **权限**(挂接 R12 矩阵):查看/搜索=全部项目成员;建库/编辑空模板页面/导入/同步/删库=owner/editor;超管按 R19 等同 owner
- **依赖**:R2、R11(编辑器复用)、R12、R18(导入完成通知)、R19
- **异常与边界场景**:
  - 平台限制(可配置):单知识库页面 ≤ 500、单文件 ≤ 1MB,超限跳过并在导入结果中提示
  - 导入快照后**相对路径图片/链接失效**:渲染时标注"资源未导入";绝对 URL 正常渲染
  - path 冲突(非法字符/重名):自动加后缀 `-1`
  - 导入超时(5 分钟)失败:可重试;已拉取部分不入库(整体成功或失败)
  - 空模板与导入型**不可互转**;导入型不可追加平台侧页面
  - 多人并发编辑同一页面:后保存覆盖前者(与 R11 同策略,不锁定)
  - 删除仓库内源文件后同步:该页面从知识库中移除(以仓库为准)
- **验收标准**:
  1. 空模板知识库:新建页面、Markdown 编辑保存、渲染正确(代码高亮)
  2. 导入型:从指定仓库多个目录导入 .md,保留目录层级成树
  3. 导入型只读:前端无编辑入口,API 写操作 403
  4. 重新导入刷新内容,last_synced_at 更新
  5. 仓库不可用时同步失败但快照保留
  6. 树形导航 + 全文搜索可用
  7. viewer 只读,前后端双重拦截;editor 可建库编辑,与 R12 矩阵一致

### R21:全局 Dashboard(我的工作台)

- **描述**:登录后默认首页。展示与当前用户**相关的**(created_by=本人,Q21)需求/开发任务/测试任务/发布任务四类数据的**统计卡片**(按状态分布)+ 每类**最近 5 条**列表(Q24),点击进入详情
- **触发场景**:登录成功后默认进入(R1)/ 左侧导航点击"工作台"
- **前置条件**:R1 登录
- **边界定义**:
  - 做什么:
    - 四张统计卡片,仅统计 **created_by=当前用户** 的数据:
      | 卡片 | 统计维度 | 数据来源 |
      |---|---|---|
      | 需求 | 按 R3 status 分布 | requirements where created_by=me |
      | 开发任务 | 按 R4 status 分布 | tasks(type=dev)where created_by=me |
      | 测试任务 | 按 R4 status 分布 | tasks(type=test)where created_by=me |
      | 发布任务 | 按 R4 status 分布 | tasks(type=release)where created_by=me |
      - 注:打磨任务(type=requirement)不单列,其进展随需求维度体现
    - 每类"最近 5 条"列表:标题 / 所属项目 / 状态 / 更新时间,按 updated_at 倒序;点击行跳转项目内详情页
    - 空态:无数据显示引导文案;无项目时引导"创建项目或等待邀请"
  - 不做什么:
    - 不做实时自动刷新(进入页面拉取一次;变更感知走 R18 toast/站内信)
    - 不做卡片自定义 / 拖拽布局 / 趋势图表
    - 不做"指派给我的"(V1 无指派概念,范围外)
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 登录成功 | 跳转 Dashboard(R1) | 工作台 |
  | 点击卡片 | 跳转对应四维管理菜单(R22) | R22 |
  | 点击列表行 | 跳转项目内需求详情 / 任务工作台 | 详情 |
  | 用户被移出项目 | 该项目历史数据不再出现(按成员资格过滤) | |
- **依赖**:R1、R3、R4
- **异常与边界场景**:
  - 成员资格变更即时影响可见范围(下次拉取生效)
  - 统计与列表允许毫秒级不一致(同窗口查询,不做事务绑定)
- **验收标准**:
  1. 登录后默认进入 Dashboard
  2. 卡片数字与四维菜单按"我创建的"口径统计一致
  3. 每类最近 5 条可点击进入正确详情页
  4. 空数据/无项目空态引导正确

### R22:四维管理菜单(需求/任务/测试/发布)

- **描述**:左侧导航「项目管理」下新增**需求管理 / 任务管理 / 测试管理 / 发布管理**四个二级菜单,分别从四个维度**跨项目聚合**展示用户**成员项目**的数据(超管=所有项目,R19,Q22);支持筛选与**快速创建**(Q23)

  导航结构(增量后):
  ```
  左侧导航
  ├── 工作台(Dashboard,R21)
  ├── 项目管理
  │    ├── 项目列表(现有)
  │    ├── 需求管理 / 任务管理 / 测试管理 / 发布管理(R22,新增)
  ├── 用户中心(个人设置 / 通知,现有)
  └── 平台管理(仅超管:平台设置 / Runner 管理 / 用户管理 / 审计日志,R19)
  ```
- **触发场景**:左侧导航 → 项目管理 → 四维管理菜单
- **前置条件**:R1 登录;R12 项目成员(或 R19 超管)
- **边界定义**:
  - 做什么:
    - 数据范围:**用户是成员的所有项目**对应数据汇总;超管可见所有项目(操作审计记 superadmin 身份)
    - 通用列表能力:项目筛选(下拉)/ 状态筛选 / 标题关键字搜索 / updated_at 倒序 / 分页(默认 20/页)
    - 通用列:标题 / 所属项目 / 状态 / 创建人 / 更新时间;特定列:
      - 需求管理:+ 优先级 / 需求分支
      - 任务管理:+ 类型(打磨/开发/测试/发布)/ Runner
      - 测试管理:+ 用例通过情况(通过/总数)
      - 发布管理:+ 部署 URL(可点击)/ 部署端口
    - **快速创建**(表单带项目下拉,默认当前筛选项目;前置校验与项目内入口**完全一致**):
      | 入口 | 流程 | 前置校验 |
      |---|---|---|
      | 新建需求 | 选项目 → R3 表单 | 无(创建后自动建分支) |
      | 新建开发任务 | 选项目 → 选 approved 需求 → 填描述 | R4 token 校验 + R5 需求 approved |
      | 新建测试任务 | 选项目 → 选需求 | R6 至少一个 dev done |
      | 新建发布任务 | 选项目 → 选需求 → 填 deploy_port | R7 至少一个 test passed + 端口全平台唯一 |
      - 前置不满足时下拉置灰并提示原因(如"该需求尚无通过的测试任务")
    - 点击行 → 跳转项目内详情页
  - 不做什么:
    - 不做跨项目批量操作
    - 不做看板/甘特视图(已在范围外)
    - 不做自定义列 / 列配置持久化
    - 不做全局全文搜索(仅标题关键字 + 筛选)
    - **项目详情内原有 Tab 与列表保持不变**(四维菜单是聚合视图,不替代项目内视图)
    - 归档/软删项目数据不出现在列表与筛选中
- **字段定义**:无新表;四个聚合查询接口复用 R3/R4 数据:
  | 菜单 | 数据源 | 过滤条件 |
  |---|---|---|
  | 需求管理 | requirements | project_id ∈ 我的成员项目(超管=全部) |
  | 任务管理 | tasks | 同上 |
  | 测试管理 | tasks(type=test) | 同上 |
  | 发布管理 | tasks(type=release) | 同上 |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 进入菜单 | 拉取成员项目列表 + 默认全项目第一页 | 列表 |
  | 快速创建 | 表单带项目下拉;选中项目后按该项目上下文执行原创建流程与全部前置校验 | 跳详情/工作台 |
  | 快速创建任务 | 仍校验创建者已绑定 GitLab token(R4),未绑定引导个人设置 | 拦截/引导 |
  | viewer 进入 | 可查看成员项目数据;新建按钮隐藏,API 写操作 403 | 只读 |
  | 超管进入 | 可见所有项目;快速创建可选任意项目;审计记 superadmin 身份 | |
  | 非任何项目成员 | 空态引导;新建按钮置灰 | 空态 |
- **依赖**:R3、R4、R5、R6、R7、R12、R19
- **异常与边界场景**:
  - 快速创建的前置校验(需求状态/端口冲突/token)与项目内入口**完全一致**,不因入口不同放宽
  - 项目筛选下拉支持搜索(单用户 ≤50 项目,量级可控)
  - 列表非实时推送,进入/筛选时刷新
  - 越权访问非成员项目数据:查询结果过滤,直接指定 project_id 的 API 返回 403
- **验收标准**:
  1. 四个菜单分别展示成员项目汇总数据,项目/状态筛选与分页可用
  2. 超管可见所有项目;普通用户非成员项目数据不可见,越权 API 返回 403
  3. 快速创建四类入口可用,前置校验与项目内一致(不满足时置灰+原因)
  4. viewer 只读(按钮隐藏 + API 403)
  5. 点击行跳转正确详情页;归档/软删项目数据不出现

### R23:平台默认 LLM 配置与项目回退链

- **描述**:平台设置新增**项目默认模型配置**(单组 url+key+model);项目未配置模型时,任务执行与所有平台内 LLM 调用自动回退使用平台默认,形成「项目级 → 平台级」统一回退链(2026-09-23 增量3,Q30–Q32)
- **触发场景**:超管在"平台管理 → 平台设置 → 模型默认配置"分组配置 / 项目未配模型时创建任务
- **前置条件**:R19(超管);R13(项目级模型配置既有逻辑)
- **边界定义**:
  - 做什么:
    - `platform_settings` 新增 3 键:`llm_base_url` / `llm_api_key` / `llm_model`,**单组**;api_key AES-GCM 加密落盘(同 `gitlab_bot_token` 模式),GET 回显打码
    - 保存时连通性测试(`GET {base_url}/models`),失败整批拒绝(沿用 R13 规则)
    - 回退链(**统一适用于所有平台内 LLM 调用点**,Q32):项目存在启用中的模型配置 → 用项目自己的(is_default 优先);项目无启用配置 → **回退平台默认**;两者皆无 → 任务/AI 入口禁用并引导(维持 R13 现状)
    - 任务启动时的**会话级临时切换优先级最高**,回退链不变
    - R13"未配置时入口禁用"的判定改为「项目级与平台级**均**未配置才禁用」
    - 项目设置模型 Tab:未配置时显示"未配置时将使用平台默认配置"提示 + 平台默认**只读回显**(base_url/model 明文,key 打码)
    - SDK 模式与 CLI 模式(env 注入)均使用回退后的最终生效配置
  - 不做什么:
    - 不做平台级主/备多组(V1 单组)
    - 不做项目级"禁用回退"开关(项目未配置一律回退)
    - 不做配置变更对**运行中任务**的生效(仅影响新任务)
- **字段定义**(platform_settings 新增键):
  | 键 | 类型 | 必填 | 校验规则 | 说明 |
  |---|---|---|---|---|
  | llm_base_url | url | 是 | http(s) 地址且非空(平台设置既有 url 校验) | OpenAI 兼容 endpoint |
  | llm_api_key | secret | 是 | 非空 ≤255;AES-GCM 加密落盘 | 接口永不回显完整 |
  | llm_model | string(64) | 是 | 非空 | 模型名(claude-sonnet-5 / gpt-5 / deepseek-chat 等) |

  - 三键作为**一个整体**保存(任一缺失/非法整批拒绝),不支持只更新其中一键
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 超管保存模型默认配置 | 三键整体校验 + `GET {base_url}/models` 连通测试,失败整批拒绝并提示 | 保存成功 |
  | 项目未配模型创建任务 | 自动回退平台默认,任务正常启动 | running |
  | 项目已配模型 | 项目配置优先,不读平台默认 | - |
  | 平台与项目均未配置 | 任务/AI 入口禁用,引导:超管配平台默认 / 项目 owner 配项目级 | 拦截 |
  | 平台默认配置变更/清空 | 即时对新任务生效;不影响进行中任务 | - |
  | 项目设置模型 Tab(未配置) | 显示回退提示 + 平台默认只读回显(key 打码) | - |
- **依赖**:R13、R19、R2(任务入口)
- **异常与边界场景**:
  - 加密密钥与现有平台级 AES key 同源,泄露处理同 R1
  - 连通测试通过但模型名错误:运行时才发现,任务 failed(与 R13 项目级同口径,不做模型名白名单)
  - 打码规则沿用平台设置现有 mask(前 5 + 掩码 + 后 4)
- **验收标准**:
  1. 超管可保存/更新模型默认配置,连通测试失败被拒绝,key 加密落盘且接口打码
  2. 项目未配模型时创建任务,SDK 与 CLI 两种模式均使用平台默认 LLM 跑通
  3. 项目配置了自己的模型后,任务使用项目配置而非平台默认
  4. 项目与平台均未配置时入口禁用并引导
  5. 项目设置模型 Tab 显示回退提示与平台默认只读回显

### R24:平台设置页布局改版

- **描述**:平台设置页从"单页平铺三个 Section"改为**左侧分类导航 + 右侧表单卡片**的设置中心形态(2026-09-23 增量3,Q33–Q34),解决内容少、横跨一屏显空的问题;新增"模型默认配置"分组(R23)
- **触发场景**:超管进入"平台管理 → 平台设置"
- **前置条件**:R19(超管)
- **边界定义**:
  - 做什么:
    - 左侧垂直分类导航 4 组:**GitLab 集成 / 域名配置 / 全局参数 / 模型默认配置**(R23 新增)
    - 点击分类切换右侧表单,当前分类高亮;各分组独立的保存按钮与"测试连接"(GitLab)行为不变
    - 视觉:表单卡片约束最大宽度,不再整行横垮
  - 不做什么:
    - 不改平台管理一级导航(平台设置/Runner 管理/用户管理/审计日志/Skills 市场排布不动,Q34)
    - 不改各设置项的校验/加密/存储逻辑(除 R23 新增 3 键)
    - 不做设置项搜索/权限细分
- **字段定义**:无新字段(仅 UI 重排;R23 的 3 键归入"模型默认配置"分组)
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 进入页面 | 默认定位第一组(GitLab 集成),加载全部配置(接口不变) | |
  | 切换分类 | 右侧切换对应表单;未保存修改不跨组保留(V1 直接丢弃,以后保存为准) | |
  | 保存 | 各分组保存逻辑与校验规则维持现状(模型默认配置按 R23) | |
- **依赖**:R19、R23
- **异常与边界场景**:
  - 切换分组丢弃未保存修改:V1 可接受;防误丢脏检查留后续
- **验收标准**:
  1. 四个分组导航可切换,默认分组正确
  2. 原有保存/测试连接/打码回显行为回归不破坏
  3. 新分组(模型默认配置)按 R23 可用
  4. 布局不再出现单组内容横垮整屏的空旷形态

### R25:审计日志全量接入

- **描述**:R19 的 `audit_logs` 表、audit_service 与查询页已建,但后端**仅用户管理 1 处接入**;本需求把非功能"全量审计"清单全部接入,并清除 `platform_settings.update` 与终端破坏性命令两处 TODO(2026-09-23 增量3,Q35–Q36)
- **触发场景**:各业务操作发生时自动写审计 / 超管在审计日志页查询
- **前置条件**:R19(audit_logs 表与 audit_service 已存在)
- **边界定义**:
  - 做什么(Q35 确认的事件清单):
    | 模块 | 事件 |
    |---|---|
    | 认证 | 登录成功 / 登录失败 / 登出 |
    | 项目 | 创建 / 更新 / 软删 / 归档 / 仓库绑定 / 仓库解绑 |
    | 成员 | 邀请 / 移除 / 角色变更 |
    | 模型配置 | 新增 / 修改 / 删除(R13) |
    | 平台设置 | 更新(记录变更键列表) |
    | Runner | 新建 / 禁用 / 启用 / 重置 token / 删除 |
    | 用户管理 | 禁用 / 启用 / 平台邀请创建 / 撤销 |
    | 需求 | 评审通过 / 驳回 / 取消 |
    | 任务 | 销毁前强制 push / 终端破坏性命令 |
    | 部署 | 发布成功 / 下线 |
  - 不做什么:
    - 不做审计日志导出/删除/修改(只读追加)
    - 不记录业务失败操作(除登录失败,Q36)
    - 不改审计查询页现有功能(过滤维度已覆盖)
- **字段定义**:无新表;复用 `audit_logs`(user_id / operator_role / action_type / project_id / target_type / target_id / detail / ip / created_at)
  - `detail` 规范(Q36):关键参数 JSON(如 `{"keys":["gitlab_url"]}`、`{"member":"<手机号脱敏>","role":"editor"}`),敏感值打码,**不记请求全文**
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 清单内操作成功 | 写一条审计(同步事务内或异步队列,沿用现有 audit_service 机制,写失败不阻塞业务) | audit_logs +1 |
  | 登录失败(密码错/锁定/账号禁用) | 写审计 `login_failed`,记 IP | 安全事件留痕 |
  | 终端破坏性命令 | 写审计(R9 TODO 清除),detail 含命令摘要 | |
  | 查询 | 现有审计日志页按时间/用户/操作类型过滤即可查到 | |
- **依赖**:R19;各事件所属需求点(R1 / R2 / R3 / R7 / R8 / R12 / R13 / R16)
- **异常与边界场景**:
  - 审计写入失败不阻塞业务(现有重试 + 告警机制)
  - 保留期 365 天清理不变(`sweep_audit_retention`)
  - 超管操作审计记录 `operator_role=superadmin`(R19 已定)
- **验收标准**:
  1. 清单每一类事件操作后,`audit_logs` 均有记录且字段完整(操作者/角色/动作/项目/目标/时间/IP)
  2. 登录失败有记录;业务操作失败无记录
  3. `detail` 无敏感明文(api_key / token 打码)
  4. `platform_settings.update` 与终端破坏性命令两处 TODO 已清除
  5. 审计日志查询页可过滤查到全部新事件
  6. 审计写入失败不影响业务操作成功

### R26:Runner 管理终端

- **描述**:Runner 管理页(超管)增加"终端"操作:打开 **Runner 宿主机 shell**(进入 runner 容器的交互终端,Q37),用于运维排障(`docker ps` / 看日志 / 查磁盘),复用现有 Web 终端通道(R9)(2026-09-23 增量3,Q37–Q38)
- **触发场景**:Runner 管理页列表行操作"终端"(仅 online Runner)
- **前置条件**:R19(超管);R16(Runner online);R9(终端通道)
- **边界定义**:
  - 做什么:
    - Runner 列表 online 行新增"终端"按钮,点击打开 Web 终端(shell = runner 容器内 shell)
    - 复用现有终端 WS 通道与限流机制(会话对象从任务容器换成 Runner)
    - 破坏性命令审计(R25 接入后入库;现有结构化告警日志保留)
    - 非 online(offline/disabled)Runner 终端按钮置灰不可点
  - 不做什么:
    - 不做进入该 Runner 上**任务容器**的 exec 终端(任务工作台已覆盖)
    - 不做多 Tab / 多会话 / 会话恢复(V1 单会话,刷新即断,Q38)
    - 不做终端录制回放、文件上传到 Runner
- **字段定义**:
  | 字段 | 类型 | 必填 | 默认值 | 说明 |
  |---|---|---|---|---|
  | session_id | uuid | 是 | auto | 复用 R9 会话模型;task_id 为空,runner_id 必填 |
  | runner_id | ref(R16) | 是 | - | 目标 Runner |
  | shell | string | 是 | /bin/bash | runner 容器内 shell |
  | opened_by | ref(R1) | 是 | - | 必须超管(后端校验) |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 点击"终端"(online) | 后端校验超管 + Runner online → 向该 Runner 下发 exec 指令(shell 挂 runner 容器)→ 建立 WS 会话 | 可交互 |
  | Runner offline/disabled | 按钮置灰;直接调 API 拒绝 | 拦截 |
  | 非超管调用 | API 403,前端无入口(前后端双重拦截) | |
  | 输出 | 复用限流(> 1000 块/秒丢弃中间) | |
  | 关闭/断开 | 销毁 pty 会话 | |
- **依赖**:R16、R9、R19、R25(审计)
- **异常与边界场景**:
  - runner 容器重启 → 会话断开,重新点击重开(V1 不自动重连)
  - Runner 机器失联 → WS 断开并提示"Runner 连接中断"
  - 宿主机 shell 权限 = runner 容器内权限(非宿主机 root),V1 接受该边界
- **验收标准**:
  1. online Runner 可打开终端并交互执行 `docker ps` 等命令,输出实时回显
  2. 非 online Runner 按钮置灰,API 拒绝
  3. 非超管无入口且 API 403
  4. 破坏性命令写入审计日志
  5. 关闭页面会话销毁,无残留 pty

### R27:项目创建 manual 绑定修复与错误细分

- **描述**:修复 manual 绑定主仓库的**权限判定缺陷**,并把失败提示从统一的"仓库 URL 无效或无权限"**细分为五类可自查的错误**(2026-09-23 增量3,Q39–Q40)
- **触发场景**:项目创建/追加绑定仓库选择"绑定已有 repo",粘贴 GitLab 仓库地址
- **前置条件**:R2;平台 GitLab 已配置(R19 平台设置)
- **根因分析**(2026-09-23 排查):
  - 平台配置 `gitlab_url=http://gitlab.zhanqirsj.com` 与用户粘贴的 `http://47.111.69.64/monorepo/sjzs.git` 为**同一 GitLab 实例**(域名解析同 IP);URL 帖 IP 不影响查询(`parse_repo_path` 仅取 path,host 不参与)
  - **缺陷**:`bot_check_repo_permission` 只读 `permissions.project_access`(bot 直接成员权限),忽略 `permissions.group_access`(组继承)——bot 通过 group 继承获得权限时 access_level 取 0,被误判"无权限"
  - 所有失败路径(404 / 403 / 权限不足 / URL 非法)折叠为同一错误码与文案,排障困难
  - 报错文案推定为"仓库 URL 无效或无权限"(Q39,rd-dev 修复后以真实地址复现验证)
- **边界定义**:
  - 做什么:
    - 权限判定修复:access_level 取 **max(project_access, group_access)**,仍要求 ≥ Maintainer(40)
    - 错误细分五类(Q40):「仓库不存在」/「平台 bot 无访问权限」/「bot 权限不足(需 Maintainer 及以上)」/「URL 格式非法」/「GitLab 连接失败」;追加绑定仓库同口径
    - 每类错误附自助排查指引(如"请联系管理员将平台 bot 加入 {namespace} 组")
  - 不做什么:
    - 不做多 GitLab 实例支持(R2 范围外不变:URL host 不参与查询,一律以平台配置的 gitlab_url 为准)
    - 不做绑定时对 repo 分支/commit 的额外校验
    - 不改 auto 建仓流程
- **字段定义**:无新字段;细分信息在错误 message 中体现(错误码族是否拆子码留给 rd-plan)
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 粘贴 IP/域名形式 URL(同一实例) | 仅取 path 查询,绑定成功 | 项目创建成功 |
  | repo 不存在(404) | 提示"仓库不存在,请检查 namespace/repo 名" | 停留创建页 |
  | bot 无访问(403) | 提示"平台 bot 无访问权限"+ 指引 | |
  | bot 权限 < Maintainer | 提示"平台 bot 权限不足(需 Maintainer)" | |
  | URL 无法解析出 namespace/repo | 提示"URL 格式非法" | |
  | GitLab 网络失败 | 提示"GitLab 服务连接失败,请稍后重试" | |
- **依赖**:R2、R19(平台设置)
- **异常与边界场景**:
  - 群组继承多层嵌套(子 group):以 GitLab API 返回的 permissions 为准,不自行递归查询
  - 修复回归:auto 建仓、追加绑定、需求建分支不受影响
- **验收标准**:
  1. 帖 `http://47.111.69.64/monorepo/sjzs.git`(实际存在的仓库)可成功创建项目;bot 靠 group 继承权限时判定正确
  2. 五类错误提示按实际失败原因正确区分
  3. auto 建仓与追加绑定回归通过
  4. 真实失败原因可被用户按提示自行排查解决

### R28:用户信息修改增强(昵称、头像本地上传)

- **描述**:在 R1 基础上增强用户个人信息修改能力,新增**头像本地上传**与**头像移除**,优化头像交互体验(2026-09-23 增量4,Q41–Q44)
- **触发场景**:登录用户在「个人设置 → 个人资料」页修改昵称、上传头像
- **前置条件**:已登录;仅可修改本人信息
- **边界定义**:
  - 做什么:
    - **昵称修改**:长度校验 1-32 字符,不唯一,可为空(空则回显手机号)
    - **头像本地上传**:选择图片文件 → 本地预览 → 上传到平台服务端 → 返回 avatar_url → 即时更新前端显示
    - **头像移除**:恢复默认头像(首字母+颜色,对齐现有 `getAvColor`/`getInitial` 逻辑)
    - **头像访问 URL**:`GET /api/files/avatars/{filename}`,公开可访问(无需登录)
  - 不做什么:
    - 不做头像裁剪(V1 仅本地预览,后端可居中裁剪缩略图)
    - 不做第三方头像集成(Gravatar/微信/QQ 等)
    - 不改手机号(R1 已确认不可改)
    - 不做头像审核(平台内部使用,信任用户)
- **字段定义**(User 表变更):
  | 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
  |---|---|---|---|---|---|
  | avatar_url | string(255) | 否 | null | 合法 URL 或平台相对路径 | 外部 URL 或本地上传后的平台路径 |
  | avatar_file_path | string(255) | 否 | null | - | 本地上传的文件存储路径(如 `./data/avatars/{user_id}/{filename}`) |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 选择图片文件 | 前端本地预览(即时显示) | 预览区显示图片 |
  | 点击上传 | 前端校验格式(JPG/PNG/WebP)和大小(≤2MB)→ 上传 | 成功则更新 avatar_url,失败则提示原因 |
  | 格式不支持 | 前端拒绝并提示"仅支持 JPG/PNG/WebP" | 停留当前页 |
  | 大小超限 | 前端拒绝并提示"图片不能超过 2MB" | 停留当前页 |
  | 上传成功 | 后端保存文件到 `./data/avatars/{user_id}/`,更新 user.avatar_url 和 avatar_file_path | 返回 { avatar_url } |
  | 点击移除头像 | 确认后清空 avatar_url 和 avatar_file_path | 显示默认头像(首字母+颜色) |
  | 网络失败 | 提示"上传失败,请重试" | 停留当前页 |
- **依赖**:R1(用户体系)
- **异常与边界场景**:
  - 上传过程中网络中断:提示重试,不产生脏数据
  - 重复上传:新文件覆盖旧文件,旧文件可异步清理(V1 可不做)
  - 头像文件被删除但 avatar_url 仍存在:前端加载失败时回退到默认头像
  - 昵称清空:回显手机号(对齐 R1 默认值逻辑)
- **验收标准**:
  1. 昵称修改保存后即时生效,长度校验正确
  2. 头像本地上传成功,预览 → 上传 → 显示闭环
  3. 头像移除后显示默认头像
  4. 格式/大小限制前端校验正确
  5. 头像 URL 公开可访问(无需登录)

### R29:平台导览(左下角入口)

- **描述**:完成侧栏底部「平台导览」功能,提供**编号链接列表**形式的静态导览(对齐 vp 原型),支持首次登录自动弹出与手动重播(2026-09-23 增量4,Q45–Q47)
- **触发场景**:新用户首次登录自动弹出;老用户点击侧栏底部「开始导览」手动触发
- **前置条件**:已登录
- **边界定义**:
  - 做什么:
    - **导览入口**:侧栏底部常驻「平台导览」卡片(对齐 vp 原型 `.tour`)
    - **首次自动弹出**:首次登录后自动弹出导览弹窗,完成后不再自动弹出
    - **静态链接列表**:编号步骤(1-10),点击跳转对应页面
    - **步骤动态生成**:根据当前用户可访问数据动态显示/隐藏步骤
    - **完成标记**:localStorage 存储 `tour_completed`
  - 不做什么:
    - 不做交互式分步引导(driver.js 高亮元素+浮层)
    - 不做视频教程
    - 不做导览进度跟踪(已完成步骤打勾等)
    - 不做多语言导览(V1 仅中文)
- **导览步骤定义**(Q46 确认,动态生成):
  | 步骤 | 标题 | 链接 | 显示条件 |
  |---|---|---|---|
  | 1 | 工作台 · Dashboard | `/` |  always |
  | 2 | 四维管理 · 需求管理 | `/manage/requirements` | always |
  | 3 | 项目 · 项目详情 | `/projects/{project_id}` | 存在项目 |
  | 4 | 需求详情(开发中) | `/requirements/{req_id}` | 存在需求 |
  | 5 | 开发工作台 · Claude 运行中 | `/tasks/{task_id}` | 存在开发任务 |
  | 6 | 测试任务 · 用例与报告 | `/tasks/{task_id}` | 存在测试任务 |
  | 7 | 发布任务 · 已上线 | `/tasks/{task_id}` | 存在发布任务 |
  | 8 | 归档时间线 | `/archive/{req_id}` | 存在已归档需求 |
  | 9 | 知识条目 | `/knowledge` | always |
  | 10 | 用户管理 / 审计日志(超管) | `/admin/users` 或 `/admin/audit-logs` | role=superadmin |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 首次登录 | 检查 localStorage 无 `tour_completed` → 自动弹出导览弹窗 | 弹窗显示 |
  | 点击步骤链接 | 跳转到对应页面,关闭弹窗 | 页面跳转 |
  | 点击"完成导览" | 关闭弹窗,写入 `tour_completed` | 不再自动弹出 |
  | 点击"跳过" | 关闭弹窗,写入 `tour_completed` | 不再自动弹出 |
  | 后续登录 | 检测到 `tour_completed` → 不自动弹出 | 侧栏入口可手动打开 |
  | 侧栏点击"开始导览" | 打开导览弹窗(无论是否已完成) | 弹窗显示 |
- **依赖**:R1(登录)、R21(Dashboard)、R22(四维管理)
- **异常与边界场景**:
  - 新用户无项目/需求/任务:对应步骤不显示,仅显示 always 步骤
  - 清理浏览器缓存:`tour_completed` 丢失,重新弹出一次(可接受)
  - 导览过程中页面跳转:弹窗关闭,下次手动打开重新开始
  - 链接目标页面数据已删除:正常 404 处理
- **验收标准**:
  1. 首次登录自动弹出导览,完成后不再弹出
  2. 步骤根据用户数据动态显示/隐藏
  3. 点击步骤正确跳转
  4. 侧栏入口常驻,可随时手动打开
  5. 跳过/完成后 localStorage 标记正确

### R30:黑白主题切换

- **描述**:平台支持亮色/暗色主题切换,覆盖核心布局组件,Monaco 编辑器和终端保持暗色(2026-09-23 增量4,Q48–Q50)
- **触发场景**:用户手动切换(顶部栏按钮);首次访问默认跟随系统
- **前置条件**:无
- **边界定义**:
  - 做什么:
    - **亮色/暗色切换**:顶部栏右侧(铃铛旁)太阳/月亮图标按钮
    - **默认跟随系统**:`prefers-color-scheme` 检测
    - **localStorage 持久化**:存储 `theme` 字段(`light`/`dark`)
    - **CSS 变量切换**:`[data-theme="dark"]` 覆盖 `:root` 变量
    - **核心布局覆盖**:侧栏、顶栏、卡片、表格、表单、按钮等基础组件
  - 不做什么:
    - 不做多主题(仅亮/暗两套)
    - 不做自定义配色(用户不可调色)
    - 不做 Monaco 编辑器主题切换(保持 `vs-dark`)
    - 不做终端主题切换(保持 `--term-bg: #0e1116`)
    - 不做 SSR/内联脚本优化防 FOUC(V1 接受短暂闪烁)
    - 语义色不随主题变(红/绿/蓝/琥珀色徽章保持固定色值)
- **字段定义**(localStorage):
  | 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
  |---|---|---|---|---|---|
  | theme | string | 否 | system | light/dark | localStorage 存储;system 表示跟随系统 |
- **交互规则**:
  | 场景/条件 | 行为/规则 | 结果/去向 |
  |---|---|---|
  | 首次访问(无 localStorage) | 检测 `prefers-color-scheme`,设置 `data-theme` | 跟随系统 |
  | 点击切换按钮 | 切换 `data-theme`,更新 localStorage | 即时生效 |
  | 系统主题变更 | 若 localStorage 为 system,实时跟随 | 自动切换 |
  | 已设置 localStorage | 使用存储值,不跟随系统 | 保持用户选择 |
- **依赖**:无(纯前端)
- **异常与边界场景**:
  - 浏览器不支持 `prefers-color-scheme`:默认亮色
  - localStorage 被禁用:每次访问跟随系统(V1 接受)
  - 页面加载闪烁(FOUC):接受短暂闪烁(<100ms)
  - 硬编码颜色:部分 inline style 或第三方组件可能不跟随主题,V1 允许存在
- **验收标准**:
  1. 亮色/暗色切换即时生效,无页面刷新
  2. 刷新后保持用户选择的主题
  3. 首次访问正确跟随系统主题
  4. 核心布局组件(侧栏/顶栏/卡片/表格/表单)颜色正确切换
  5. Monaco 编辑器和终端保持暗色不变

## 非功能需求

| 类别 | 要求 |
|---|---|
| **性能** | 项目首页 < 2s;任务容器冷启动 < 30s(含 git clone);Claude 首 token < 3s(取决于配置的模型) |
| **并发** | 单实例 ≥ 50 并发容器;单项目 ≤ 3 并发任务(不含部署中);单用户 ≤ 5 同时运行容器;单项目 ≤ 5 部署 |
| **安全** | 密码 bcrypt;JWT;api_key/GitLab token AES-GCM 加密;容器间网络隔离;容器出网白名单(LLM endpoint + GitLab + 包管理镜像源) |
| **审计** | 登录/项目增删/成员变更/部署/模型配置变更/驳回操作/强制 push 全量审计日志,保留 1 年;查询入口为超管审计日志页(R19) |
| **可用性** | ≥ 99%(V1 单实例,接受短时维护窗口) |
| **数据备份** | MySQL 每日备份保留 7 天;**代码与文档以 GitLab 为唯一事实源**(平台不备份 GitLab,GitLab 自有备份) |
| **浏览器** | Chrome / Edge 最近两个大版本;Safari 不保证(V1) |
| **国际化** | V1 仅中文界面 |

## 范围外(V1 明确不做)

- 桌面客户端 / 移动端 / 浏览器插件
- 第三方登录(OAuth/SSO/手机号)
- 组织/团队层级
- GitHub / Gitee 等其他 Git 托管(V1 仅 GitLab)
- 自定义容器镜像 / docker-compose 多容器 / SSH 直连
- 宿主机挂载持久化(V1 数据全走 GitLab,容器是纯计算资源)
- 多人实时协同编辑(光标共享/CRDT)
- LSP / 智能补全 / Git 可视化操作面板
- 需求优先级看板 / 排期 / 甘特图
- 任务级 MR(评审走最终 merge)
- 性能测试 / 压测 / 第三方测试平台集成
- 多环境部署 / 回滚 / 蓝绿 / HTTPS(域名策略 Q28/Q29:预览/部署根域名入平台设置;发布任务可自定义对外域名,均 V1 仅 HTTP、不含证书/DNS 托管)
- 配额 / 限流 / 计费
- 知识条目版本管理 / 推荐
- 知识库空间:自动同步 / 回写仓库 / 页面版本历史 / 平台级知识库空间 / 导出 PDF / 非 .md 文件导入
- Dashboard/四维管理:实时刷新 / 自定义卡片 / 趋势图表 / 跨项目批量操作 / "指派给我的"视图 / 自定义列
- 平台默认 LLM 主/备多组(V1 单组,R23)
- Runner 终端:进入任务容器 exec / 多 Tab 会话 / 录制回放 / 文件上传(R26)
- 审计日志导出(R25)
- 内嵌 MySQL/Redis 容器
- 头像裁剪(R28,V1 仅预览)
- 交互式分步导览(driver.js 高亮元素,V1 做静态链接列表,R29)
- 多主题/自定义配色(R30,V1 仅亮/暗两套)

## 设计稿引用

无(平台类产品,UI 参考 MonkeyCode / v0.dev / bolt.new / Codespaces 的工作台布局,设计规范在 rd-plan 阶段定)

## 待确认清单

- [ ] R28 头像上传存储路径:`./data/avatars/{user_id}/` 是否合适?(向技术负责人确认)
- [ ] R29 导览步骤动态生成:复用现有 `/api/projects`、`/api/requirements`、`/api/tasks` 接口,还是需要聚合接口?
- [ ] R30 主题切换:暗色 CSS 变量值是否需对照 vp 原型或参考 GitHub Dark 风格?

**待确认问题汇总**(进入 rd-plan 前必须清零):
- Q41:头像上传存储路径确认
- Q42:导览步骤动态生成接口方案确认
- Q43:暗色主题 CSS 变量参考风格确认

### 已确认决策汇总

- **Q1–Q8**(2026-09-23 增量4 第一轮):
  - Q1:头像上传 → **新增本地上传**,存储平台服务端本地磁盘
  - Q2:头像限制 → **JPG/PNG/WebP,≤2MB**
  - Q3:预览与裁剪 → **本地预览必须有,裁剪 V1 不做**
  - Q4:昵称唯一性 → **不唯一,仅长度校验(1-32字符)**
  - Q5:导览形态 → **静态链接列表(对齐 vp 原型)**
  - Q6:导览触发 → **首次登录自动弹出一次,完成后侧栏入口常驻**
  - Q7:主题切换入口 → **顶部栏右侧(铃铛旁),太阳/月亮图标按钮**
  - Q8:主题持久化 → **localStorage,默认跟随系统**
- **Q9–Q14**(2026-09-23 增量4 第二轮):
  - Q9:头像存储路径 → **平台服务端本地磁盘,URL 待确认(Q41)**
  - Q10:头像上传 API → **独立接口 `POST /api/users/me/avatar`**
  - Q11:导览步骤 → **保留 10 步框架,链接动态取当前用户可访问数据**
  - Q12:新用户导览 → **动态生成步骤,只显示有数据可访问的步骤**
  - Q13:主题切换范围 → **覆盖全部页面,Monaco 编辑器和终端保持暗色**
  - Q14:主题实现方式 → **CSS 变量切换,核心布局跟随;语义色不随主题变**
- **Q15–Q20**(2026-09-23 增量4 第三轮):
  - Q15:头像文件访问 URL → **新增 `GET /api/files/avatars/{filename}`,公开可访问**
  - Q16:导览步骤动态生成 → **前端调用现有 API 获取数据,有数据则显示对应步骤**
  - Q17:首次登录判断 → **localStorage 标记 `tour_completed`**
  - Q18:主题闪烁 → **接受短暂闪烁,V1 不做 SSR/内联脚本优化**
  - Q19:头像删除/重置 → **支持,恢复默认头像(首字母+颜色)**
  - Q20:Monaco 编辑器主题 → **保持现有暗色 `vs-dark`,不随平台主题切换**

---

**历史决策汇总**(Q1–Q40,2026-09-20 至 2026-09-23 增量3):

- **Q1**:`devbox:v1` 镜像依赖清单 → 留给 `rd-arch`
- **Q2**:Claude Agent SDK 选型 → 留给 `rd-arch`(取决于后端语言)
- **Q3**:GitLab 实例 + bot token → **管理员首次登录后,在"用户中心 → 平台设置"配置**,配置前 GitLab 相关功能禁用
- **Q4**:平台管理员 → **角色**(可多人)
- **Q5**:注册 → **邀请制**,超管/项目 owner 都可邀请
- **Q6**:测试任务 → **项目可绑定多个仓库**(main/test/docs/other),测试任务默认拉取 role=test 仓库
- **Q7**:部署单点故障 → **接受**(V1)
- **Q8**:commit 规范 → `[ai:{type}] {task_title}`,author = 用户,committer = AI,不签名
- **Q9**:开源协议 → **闭源**(V1)
- **Q10**:viewer 预览权限 → **可看**
- **Q11**:强制 push 失败兜底 → **保留容器 30 分钟重试**,超时销毁 + 告警
- **Q12**:告警通道 → **站内信 + 钉钉 webhook**(R18)
- **Q13**:bot token scope → **`api`**(bot 在目标 group 是 Owner/Maintainer 即可,不需 GitLab 管理员)
- **Q14**:用户 token scope → **`read_repository + write_repository`**(最小权限)
- **Q15**(2026-09-21):超管对未参与项目 → **全权等同 owner**(R19)
- **Q16**(2026-09-21):用户账号禁用 → **禁用即全失效**(登录拒绝 + 现有 JWT 立即失效 + 进行中任务立即取消)(R19)
- **Q17**(2026-09-21):审计日志 → **超管简单查询页**(时间/用户/操作类型过滤)(R19)
- **权限体系**(2026-09-21):统一收口为 R19;**Runner 管理仅超管可见可操作**
- **Q18**(2026-09-21):项目知识库(R20)与 R14 知识条目 → **并存**(条目级 vs 文档空间级)
- **Q19**(2026-09-21):知识库内容来源 → **导入型 = 快照导入 + 手动同步,平台内只读;空模板 = 可编辑,存平台库**
- **Q20**(2026-09-21):知识库内部结构 → **树形目录**(导入保留仓库目录层级)
- **知识库**(2026-09-21):新增 R20 项目知识库管理(空模板 / 目录导入,Markdown 组件查看)
- **Q21**(2026-09-21):Dashboard「和我相关的」→ **我创建的**(created_by)
- **Q22**(2026-09-21):四维管理菜单数据范围 → **成员项目汇总**(超管按 R19 可见全部)
- **Q23**(2026-09-21):四维菜单 → **支持快速创建**(项目下拉;前置校验与项目内一致)
- **Q24**(2026-09-21):Dashboard 形态 → **统计卡片 + 每类最近 5 条**
- **导航**(2026-09-21):新增 R21 Dashboard(登录默认页)、R22 四维管理菜单;R1 登录跳转改为 Dashboard
- **Q25**(2026-09-21):ARCH D20 网关链路 → **取消 Runner 本地代理**,网关直连 Runner 宿主机映射端口;R15/R16 已同步修订
- **Q26**(2026-09-21):文档目录规范 → 全部统一 `docs/{YYYYMMDD}_{descSlug}_{taskShortId}/`(descSlug=需求标题 slug 截断 32,taskShortId=uuid 前 8 位);归档用 `docs/{YYYYMMDD}_{descSlug}_archive/`;R3/R5/R6/R7/R14 及概念模型已同步修订
- **Q27**(2026-09-21):工作台文件树「全部/变更」双视图 → 变更=相对 base_branch 全部差异(已 commit + 未 commit),按仓库分组,类型/行数标注,点击直达 Diff;不做作者区分标注;R5/R11 及工作台图已同步修订
- **Q28**(2026-09-21 增量2):品牌定名 **「旗程」**(仅中文名,不设英文标识);预览/部署**根域名入平台设置**(`preview_base_domain` / `deploy_base_domain`,超管配置,示例值仅为默认)——域名与品牌解耦,平台上线时设置
- **Q29**(2026-09-21 增量2):**发布任务可自定义对外域名**(deploy_host,默认 `{slug}.{deploy_base_domain}` 预填可改;全平台唯一、合法主机名校验;仅 HTTP,需自行将域名解析到网关;不含证书/DNS 托管)
- **Q30**(2026-09-23 增量3):平台默认 LLM 存储 → **复用 platform_settings KV,新增 3 键(llm_base_url / llm_api_key / llm_model),单组,api_key AES-GCM 加密**(R23)
- **Q31**(2026-09-23 增量3):回退链 → **项目启用配置优先,无则回退平台默认;两者皆无才禁用入口;会话级临时切换优先级最高**(R23)
- **Q32**(2026-09-23 增量3):平台默认 LLM 生效范围 → **所有平台内 LLM 调用点统一走回退链**(R23)
- **Q33**(2026-09-23 增量3):平台设置页布局 → **左侧分类导航(GitLab 集成 / 域名配置 / 全局参数 / 模型默认配置)+ 右侧表单卡片**(R24)
- **Q34**(2026-09-23 增量3):平台管理一级导航 → **本次不动,仅平台设置页内改版**(R24)
- **Q35**(2026-09-23 增量3):审计事件清单 → **认证 / 项目 / 成员 / 模型配置 / 平台设置 / Runner / 用户管理 / 需求 / 任务 / 部署 全量接入**(R25)
- **Q36**(2026-09-23 增量3):审计记录规则 → **仅登录失败记失败事件;记操作 IP;detail 为关键参数 JSON 且敏感值打码**(R25)
- **Q37**(2026-09-23 增量3):Runner 终端对象 → **Runner 宿主机 shell(runner 容器内),用于运维排障**(R26)
- **Q38**(2026-09-23 增量3):Runner 终端交互 → **仅超管 / 非 online 置灰 / 破坏性命令审计 / V1 单会话**(R26)
- **Q39**(2026-09-23 增量3):R27 报错原文 → **推定"仓库 URL 无效或无权限"(与 `project_access`-only 判定缺陷一致);rd-dev 修复后以 `http://47.111.69.64/monorepo/sjzs.git` 复现验证**
- **Q40**(2026-09-23 增量3):manual 绑定错误 → **细分为五类可自查文案;权限判定取 project_access 与 group_access 最大值**(R27)
