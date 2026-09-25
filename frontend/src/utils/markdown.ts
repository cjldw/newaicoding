/**
 * 共享 markdown 轻量渲染 —— TaskDetail / RequirementDetail 双实现去重(BUG-019 先例口径)。
 *
 * 支持 h1-h3 / 加粗 / 行内代码 / 围栏代码块(R2 扩展)/ 无序列表 / 段落,
 * 内容先做 &<> 转义,无 XSS 面。
 * 生成纯语义标签、不带任何内联样式,排版统一由 globals.css `.md` 作用域类承接
 * (调用方容器需带 `md` 类)。
 *
 * 口径取舍:以原 TaskDetail 版为准(更安全)——
 *   1) 保留单换行 `<br/>`,纯文本草稿不塌行(原 RequirementDetail 版会吞掉单换行);
 *   2) 不把整包输出套进 `<p>`(原 RequirementDetail 版 `<p>` 内嵌 h2/li 等块级元素是
 *      非法 HTML,浏览器会提前截断 p 并残留游离闭合标签);
 *   3) 输出不依赖 Tailwind 字面类出现在 dangerouslySetInnerHTML 里(免受扫描配置影响)。
 * 原 RequirementDetail 版的 `*斜体*` / 有序列表特判未保留,差异已在迁移时说明。
 *
 * R2(条目详情页)扩展围栏代码块:```lang 代码块渲染为 `<pre class="md-code">`。
 * 实现取分段遍历(matchAll)而非占位符替换:转义在每段独立进行,代码块内容
 * 与行内语法互不污染,也不存在占位符与正文撞车的可能。围栏未闭合时该段按
 * 普通文本降级(字面展示 ```),不吞正文。样式见 globals.css `.md pre.md-code`
 * (知识库本地版 KnowledgeBaseView 的同能力不并入,R20 wiki 页独立演进,超范围)。
 */

/** 行内语法渲染(转义 + 原有替换链,顺序不动) */
function renderTextSegment(seg: string): string {
  const esc = seg
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc
    .replace(/^### (.*)$/gm, '<h3>$1</h3>')
    .replace(/^## (.*)$/gm, '<h2>$1</h2>')
    .replace(/^# (.*)$/gm, '<h1>$1</h1>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^[-*] (.*)$/gm, '<li>$1</li>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br/>')
}

/** 围栏代码块渲染:lang 仅作为 data-lang 标注(不做客户端高亮),内容转义后进 pre */
function renderFenceSegment(code: string, lang: string): string {
  const esc = code.replace(/\n$/, '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return `<pre class="md-code"${lang ? ` data-lang="${lang}"` : ''}><code>${esc}</code></pre>`
}

// 围栏开栏:``` + 可选语言词 + 行尾;闭栏:``` 单独出现。未闭合围栏不参与匹配(降级为文本)
const FENCE_RE = /```([\w+#.-]*)[ \t]*\r?\n([\s\S]*?)```/g

export function renderMarkdown(md: string): string {
  let out = ''
  let last = 0
  for (const m of md.matchAll(FENCE_RE)) {
    const start = m.index ?? 0
    out += renderTextSegment(md.slice(last, start))
    out += renderFenceSegment(m[2], m[1])
    last = start + m[0].length
  }
  out += renderTextSegment(md.slice(last))
  return out
}
