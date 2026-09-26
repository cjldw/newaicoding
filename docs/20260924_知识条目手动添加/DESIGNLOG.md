# 设计稿落地:知识条目手动添加(增量 UI 档案)

> 创建日期:2026-09-25
> 状态:进行中

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| 知识条目详情 markdown 预览(EntryDetail) | ✅ | 无新稿,样板轨:.md 作用域 + utils/markdown.ts | 升级共享渲染器全能力;KnowledgeBaseView 弃本地版,消灭第三份重复实现 |
| 知识条目详情页左右模式(左大纲+右正文) | ✅ | 无新稿,样板轨:.md/.md-toc 作用域 | 大纲自 h2/h3 提取,锚点滚动;<2 标题自动退单栏 |
| A 型条目代码工作台(左文件树+右文件预览) | ✅ | 无新稿,样板轨:同上 | 树=source_links 递归路径;点击文件右侧预览(md→markdown/代码→monaco);说明 markdown 在上方说明区 |
| A 型工作台粘性固定(关联代码区块钉屏) | ✅ | 无新稿,样板轨:.route-scroll 文档流 + sticky | 首轮全页视口固定方案被用户否决回退;终稿=页面正常滚动,「关联代码」容器 .entry-code-dock sticky 钉屏(top:8px/max-height 100vh-70),树/预览余高内滚;宽屏保留 |

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

## 落地记录:A 型代码工作台(2026-09-25)

- EntryDetail.tsx:逐路径块懒加载(useInView/CodePathBlock/DirBody/DirNode)替换为 CodeWorkbench——左 .code-tree(240px sticky,repo·branch 组头,目录折叠/文件选中蓝底 active)+ 右 .code-preview(.md→renderMarkdown / 代码→monaco 只读 / 二进制→占位;头部路径+来源+重新拉取 refresh=1)
- 数据策略:递归树随响应带 content 的文件点击零请求;无 content 按需取;默认选中第一个可预览文本文件;paths 编辑保存后复位重选
- A 型不渲染 .md-toc 大纲(showToc 加 codeSources 门控),说明 content 全宽在 workbench 上方;B 型零变化
- globals.css:.code-wb/.code-tree/.code-preview 33 行纯插入(md-toc 区段后);npx tsc -b --noEmit 0 错误;详见 .scratch/rd-ui-codetree.md
