/**
 * 共享 markdown 轻量渲染 —— TaskDetail / RequirementDetail 双实现去重(BUG-019 先例口径)。
 *
 * 仅支持 h1-h3 / 加粗 / 行内代码 / 无序列表 / 段落,内容先做 &<> 转义,无 XSS 面。
 * 生成纯语义标签、不带任何内联样式,排版统一由 globals.css `.md` 作用域类承接
 * (调用方容器需带 `md` 类)。
 *
 * 口径取舍:以原 TaskDetail 版为准(更安全)——
 *   1) 保留单换行 `<br/>`,纯文本草稿不塌行(原 RequirementDetail 版会吞掉单换行);
 *   2) 不把整包输出套进 `<p>`(原 RequirementDetail 版 `<p>` 内嵌 h2/li 等块级元素是
 *      非法 HTML,浏览器会提前截断 p 并残留游离闭合标签);
 *   3) 输出不依赖 Tailwind 字面类出现在 dangerouslySetInnerHTML 里(免受扫描配置影响)。
 * 原 RequirementDetail 版的围栏代码块 / `*斜体*` / 有序列表特判未保留,差异已在迁移时说明。
 */
export function renderMarkdown(md: string): string {
  const esc = md
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
