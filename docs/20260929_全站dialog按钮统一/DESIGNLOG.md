# 设计稿落地:全站 Dialog 按钮样式统一

> 创建日期:2026-09-29
> 状态:进行中

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| 全站 Dialog 底部按钮统一 | ✅ 完成 | (无设计稿;以 globals.css 按钮词汇表为准) | 25 个 ui/Dialog 文件代码级全量审计:0 违规残留;实际修正仅容器门卫弹框(见前目录 F1);实现 subagent 报「37 文件 3 处」因 429 中断未能回填明细,本表为主会话 grep 复核口径 |

## 需求来源

- 用户口述:排查项目所有 dialog,统一按钮样式

## 规范基准(实现时从代码固化)

- 按钮词汇表以 frontend/src/styles/globals.css 为准:`.btn`(次按钮,--surface 灰底)/ `.btn-pri`(主按钮,--primary 实底白字)/ `.btn-danger`(危险)/ `.btn-sm`(小尺寸)与 ui/Button.tsx variant(若存在),以项目主导习惯为准
- 映射:确认/主操作 → btn-pri;取消/次操作 → btn;删除/停止等危险 → btn-danger;弹框内小按钮 → 加 btn-sm

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/**/*.tsx(dialog 使用处) | 修改 | 仅按钮 className/variant 归一,零逻辑改动;盘点表回填本文件 |

## 盘点表(2026-09-29 回填;实现 subagent 初扫 + 主会话 grep 复核)

**审计方法**:25 个引用 ui/Dialog 的文件逐一扫描 `<button>` 的 className(多行属性精确匹配),另做两项全站残留扫描:① 不存在的 `btn-primary` 类 → **0 处**;② diff 新增行中非规范按钮类 → 仅 TaskDetail 门卫轮已合规产物。

**结论:全部 25 个 dialog 文件的底部操作按钮均在 `.btn` 词汇表内,无需再修**。修正集中在容器门卫弹框一处(前轮 F1:`btn-primary`→`btn btn-pri`),其余对话框(任务创建/需求编辑/MCP/Skills/用户管理/Runner 管理/知识库/Dimension/评审/发布等)走查均为以下两类合规形态:

| 形态 | 判定 | 例子 |
|---|---|---|
| `.btn` / `.btn-pri` / `.btn-danger`(+`btn-sm`) | ✅ 合规 | 全部 dialog footer 操作按钮 |
| 非 footer 控件(tab 切换 `tab`/`dchip`、下拉菜单项、文字链 `hover:underline`、卡片选择行) | ✅ 合规(不同控件类型,不套按钮体系) | SkillsManagement tab、ProjectDetail 菜单项、EntryDetail 文字链 |

- 唯一轻微项(不修,留痕):EntryDetail.tsx:416 `code-tree-retry` 自定义类按钮(文件树面板内重试,非 dialog footer,样式自洽)
- tsc:源码零新增错误(仅 `__tests__` 预存 vitest/@testing-library 缺声明)

## 占位与待办

- 无

## 待开发支持清单

- 无
