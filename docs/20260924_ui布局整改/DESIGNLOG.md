# 设计稿落地:UI 布局整改(四维管理/任务详情/设置区/全局表格)

> 创建日期:2026-09-24
> 状态:完成(浏览器核对通过)

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| 全局表格样式统一(16 处) | ✅ | 无新稿,沿用 vp + design.md token | 操作列 ops 右对齐/长文本 cell-txt/分页 foot-split/colgroup |
| 四维管理页(需求/任务/测试/发布) | ✅ | vp/index.html 范式 | 底栏合一、标题省略、命名统一 |
| 任务详情页(打磨/开发) | ✅ | vp/index.html L1442-1484 | 非 dev 两栏 .wb.n2、7 步 stepper、加载态 |
| 个人设置 3 页 | ✅ | - | 挂回 MainLayout、三页规范拉齐 |
| 平台设置 + admin 4 页 | ✅ | - | 宽屏、归范、失效类修复 |

## 设计稿来源

- `docs/20260920_ai_web开发平台/vp/index.html`(视觉原型):三栏工作台、stepper、徽章色板、按钮层级
- `design.md`:shadcn New York / zinc token / 0.5rem 圆角

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/styles/globals.css | 修改 | 删 .card 双定义;新增 .cell-txt/.ops/.foot-split/.page-loading/.wb.n2/.stp.on;wb 区内联收敛类 ~25 个;.md 作用域 |
| frontend/src/pages/tasks/TaskDetail.tsx | 修改 | 两栏切换、7 步 stepper、release 变更表、树层级、内联 42→2 |
| frontend/src/pages/manage/DimensionPage.tsx / ManagePages.tsx | 修改 | 底栏合一、中性脚注、createLabel 统一 |
| frontend/src/router.tsx / SettingsLayout.tsx / Breadcrumb.tsx | 修改 | /settings 挂回 MainLayout,面包屑映射 |
| frontend/src/pages/settings/ ×3 | 修改 | 三页规范拉齐(Card/Input/btn/保存右对齐/page-loading) |
| frontend/src/pages/admin/ ×5 | 修改 | fbar 入卡、btn-pri 失效类修复、alert→toast、colgroup、宽屏 |
| frontend/src/pages/requirements/RequirementList.tsx | 修改 | 分页入卡 foot-split、标题省略 |
| frontend/src/pages/notifications/NotificationCenter.tsx | 修改 | 内联样式回归 .tbl 体系 |
| frontend/src/utils/markdown.ts | 新增 | renderMarkdown 共享(TaskDetail/RequirementDetail 去重) |

## 占位与待办

- RequirementDetail 的 markdown 渲染行为有变化(共享版以 TaskDetail 为准):标题字号变小、code 带边框、单换行保留;失去围栏代码/斜体/有序列表特判。若需求详情页需要富 markdown,后续引入正式渲染器。
- `KnowledgeBaseView.tsx` 存在第三份 renderMarkdown,建议后续并入 utils/markdown.ts。
- dev 编辑器多文件页签(vp ed-tabs)未做,工作量大,单独立项。

## 追加:弹窗按钮与危险色统一(批 5 顺带完成)

- 根因:`tailwind.config.ts` 从未定义 `error` 色,全站 40 处 `bg-error/text-error` 伪 token 不生成样式——危险按钮白底不可读、错误提示条无底色
- 规范:弹窗 footer 取消=ghost 默认尺寸、主操作=primary、危险=danger(既有 .btn-danger 软红),弃用 footer 内 size="sm"
- 改动 15 个文件:危险钮 9 处→variant="danger"、裸 Button 补 primary 4 处、取消统一 ghost 11 处、40 处 error 伪 token→bg-red-bg/text-red-fg 主题变量

## 待开发支持清单(转后端/数据)

- **BUG-UI-071(P1)**:`backend/app/api/knowledge.py:31` 无效 import 致 `/api/requirements/:id/archive` 每页 500——删该行即可(超出 rd-ui 红线,交后端修)
- **BUG-UI-072(P3)**:超管 avatar 文件丢失 404(R19 数据遗留),需补文件或清库引用
- **BUG-UI-073(P4)**:审计详情列「JSON 摘要」断词换行,待下一轮细化
- 任务管理页 2 条历史乱码标题(DB 数据问题,非 UI)

## 核对记录

- 浏览器核对:2026-09-24,Playwright + 超管 18767169856,全部核对点 ✅
- 截图:`docs/20260920_ai_web开发平台/report/ui-overhaul-20260924/`(11 张)
- 构建:`tsc -b --noEmit` 零错误;`vite build` 通过
