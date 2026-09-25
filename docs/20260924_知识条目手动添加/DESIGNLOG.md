# 设计稿落地:知识条目手动添加(增量 UI 档案)

> 创建日期:2026-09-25
> 状态:进行中

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| 知识条目详情 markdown 预览(EntryDetail) | ✅ | 无新稿,样板轨:.md 作用域 + utils/markdown.ts | 升级共享渲染器全能力;KnowledgeBaseView 弃本地版,消灭第三份重复实现 |
| 知识条目详情页左右模式(左大纲+右正文) | ✅ | 无新稿,样板轨:.md/.md-toc 作用域 | 大纲自 h2/h3 提取,锚点滚动;<2 标题自动退单栏 |

## 设计稿来源

- 无外部设计稿;样板轨 = globals.css `.md` 作用域样式 + 现有页面写法

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/utils/markdown.ts | 修改 | 升级为全能力渲染器(链接/有序列表/引用/表格,保持转义安全与围栏代码块) |
| frontend/src/pages/knowledge/EntryDetail.tsx | 复用 | 已用共享渲染器,自动受益;必要时微调 .md 样式 |
| frontend/src/pages/knowledge/KnowledgeBaseView.tsx | 修改 | 删除本地第三份 renderMarkdown,切换到共享渲染器 |

## 占位与待办

- 无占位;数据来自现有接口

## 待开发支持清单

- 无(纯前端渲染能力升级;若未来需要更完整 markdown(图片/嵌套列表/代码高亮),建议引入 marked+dompurify,需用户确认装包)

## 落地记录:markdown 预览升级(2026-09-25)

- utils/markdown.ts 重写为全能力块级渲染器(链接/有序列表/引用/表格/斜体/围栏码,转义优先,javascript: 降级)
- KnowledgeBaseView.tsx 删本地 135 行渲染实现,切换共享版(容器加 .md 类)——全仓 renderMarkdown 定义归一
- globals.css .md 作用域补 ul/ol/table/blockquote/a 样式
- 浏览器核对:条目 d2dbfc69 注入五类语法断言全过(a/table/ol/blockquote/pre),console 0,原文已恢复;截图 report/rd-ui-markdown/
