/**
 * 共享 markdown 轻量渲染 —— TaskDetail / RequirementDetail / EntryDetail / KnowledgeBase /
 * KnowledgeBaseView 五处消费(BUG-019 先例口径,全仓唯一实现)。
 *
 * 能力基准对齐原 KnowledgeBaseView 本地版(预览升级):
 * h1-h3 / 加粗 / 斜体 / 行内代码 / 行内链接 / 围栏代码块(```lang)/ 无序+有序列表
 * (真实 <ul>/<ol> 包裹,编号各自起算)/ 引用块(递归按块渲染)/ 表格 / 段落。
 *
 * 口径取舍(继承并延续自原 TaskDetail 版):
 *   1) 转义优先:每段先 &<> 转义再做标记替换,无 XSS 面;
 *   2) 段内单换行 <br/>,纯文本草稿不塌行;
 *   3) 按块输出,不把整包套进单个 <p>(块级嵌 p 为非法 HTML,浏览器会提前截断);
 *   4) 输出为纯语义标签、不带 Tailwind 字面类(dangerouslySetInnerHTML 免受扫描配置影响),
 *      原 KnowledgeBaseView 版的内联 Tailwind 类由 globals.css `.md` 作用域等价承接
 *      (ul/ol/table/blockquote/a 样式随本次能力化补齐,调用方容器需带 `md` 类);
 *   5) 链接仅放行 http(s):// 与相对路径(/、./、../、# 或无 scheme 的裸路径),
 *      javascript:/data: 等带 scheme 的降级为纯文本;外链追加 target=_blank + rel=noopener;
 *   6) 围栏未闭合时该段降级为普通文本(字面展示 ```),不吞正文;lang 仅作 data-lang 标注
 *      (不做客户端高亮);
 *   7) h1-h3 输出带 id="md-h-{序号}"(按出现顺序,围栏代码块内的 # 行不计),
 *      extractOutline 用同一序号规则,供详情页目录锚点滚动(R28.F2)。
 */

/** 标题 id 状态:renderBlocks 递归全程共享一个计数器(引用块内的标题不编号不加 id) */
interface MdIdState { n: number }

const mdHeadingId = (st: MdIdState) => `md-h-${++st.n}`

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** 仅放行 http(s):// 与相对路径(/、./、../、# 或无 scheme 的裸路径) */
function isSafeHref(url: string): boolean {
  return /^(https?:\/\/|\/|\.\.?\/|#)/i.test(url) || !/^[a-z][a-z0-9+.-]*:/i.test(url)
}

/** 行内语法:转义 → 行内代码 → 加粗 → 斜体 → 链接(转义优先,顺序不动) */
function renderInline(seg: string): string {
  let s = escapeHtml(seg)
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (raw, text: string, url: string) => {
    if (!isSafeHref(url)) return raw
    const href = url.replace(/"/g, '%22').replace(/'/g, '%27')
    const external = /^https?:\/\//i.test(url)
    return `<a href="${href}"${external ? ' target="_blank" rel="noopener noreferrer"' : ''}>${text}</a>`
  })
  return s
}

/** 表格分隔行:| --- | :---: | 形态(每格仅由 -: 与空格构成) */
function isTableSep(line: string): boolean {
  const t = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return t.length > 0 && t.split('|').every((c) => /^ *:?-+:? *$/.test(c))
}

/** 块级解析:逐行状态机,空行分段,段内单换行 <br/> 保形(ids 传入时为 h1-h3 输出序号 id) */
function renderBlocks(src: string, ids?: MdIdState): string {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const out: string[] = []
  let para: string[] = []
  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${para.map(renderInline).join('<br/>')}</p>`)
      para = []
    }
  }
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    // 围栏代码块(未闭合降级为普通文本,不吞正文)
    if (/^```/.test(line)) {
      let end = -1
      for (let j = i + 1; j < lines.length; j++) {
        if (/^```\s*$/.test(lines[j])) { end = j; break }
      }
      if (end > i) {
        flushPara()
        const lang = line.slice(3).trim().match(/^[\w+#.-]*/)?.[0] ?? ''
        const code = escapeHtml(lines.slice(i + 1, end).join('\n')).replace(/\n$/, '')
        out.push(`<pre class="md-code"${lang ? ` data-lang="${lang}"` : ''}><code>${code}</code></pre>`)
        i = end + 1
        continue
      }
    }
    // 标题(带序号 id,与 extractOutline 同规则;引用块递归不传 ids,块内标题不参与编号)
    const h = line.match(/^(#{1,3}) (.+)$/)
    if (h) {
      flushPara()
      const level = h[1].length
      const idAttr = ids ? ` id="${mdHeadingId(ids)}"` : ''
      out.push(`<h${level}${idAttr}>${renderInline(h[2])}</h${level}>`)
      i++
      continue
    }
    // 引用块(连续 > 行;内部递归按块渲染,嵌套列表/围栏/表格均可)
    if (/^> ?/.test(line)) {
      flushPara()
      const buf: string[] = []
      while (i < lines.length && /^> ?/.test(lines[i])) {
        buf.push(lines[i].replace(/^> ?/, ''))
        i++
      }
      out.push(`<blockquote>${renderBlocks(buf.join('\n'))}</blockquote>`)
      continue
    }
    // 表格:当前行含 | 且下一行为 |---|---| 分隔行
    if (line.includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flushPara()
      const cells = (l: string) => l.trim().replace(/^\|/, '').replace(/\|$/, '')
        .split('|').map((c) => renderInline(c.trim()))
      const head = cells(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
        rows.push(cells(lines[i]))
        i++
      }
      out.push(
        `<table><thead><tr>${head.map((c) => `<th>${c}</th>`).join('')}</tr></thead>`
        + `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`,
      )
      continue
    }
    // 无序列表(真实 <ul> 包裹;- 与 * 两种记号)
    if (/^[-*] /.test(line)) {
      flushPara()
      const items: string[] = []
      while (i < lines.length && /^[-*] /.test(lines[i])) {
        items.push(`<li>${renderInline(lines[i].slice(2))}</li>`)
        i++
      }
      out.push(`<ul>${items.join('')}</ul>`)
      continue
    }
    // 有序列表(真实 <ol> 包裹,编号由 ol 生成 —— 各列表编号独立起算)
    if (/^\d+\. /.test(line)) {
      flushPara()
      const items: string[] = []
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(`<li>${renderInline(lines[i].replace(/^\d+\. /, ''))}</li>`)
        i++
      }
      out.push(`<ol>${items.join('')}</ol>`)
      continue
    }
    // 空行 = 段落分隔;其余行累计为段落(段内单换行 <br/> 保形)
    if (!line.trim()) {
      flushPara()
      i++
      continue
    }
    para.push(line)
    i++
  }
  flushPara()
  return out.join('')
}

export function renderMarkdown(md: string): string {
  return renderBlocks(md, { n: 0 })
}

/**
 * 提取 h1-h3 大纲(目录用,EntryDetail 左栏):跳过 ``` 围栏代码块内的 # 行,
 * id 序号与 renderMarkdown 输出一致(同 md-h-{序号} 规则);围栏未闭合时与渲染口径
 * 相同 —— 该段降级普通文本,后续 # 行照常计入。
 */
export function extractOutline(markdownText: string): { level: number; text: string; id: string }[] {
  const lines = markdownText.replace(/\r\n?/g, '\n').split('\n')
  const outline: { level: number; text: string; id: string }[] = []
  const ids: MdIdState = { n: 0 }
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    // 围栏代码块整段跳过(闭合判定与 renderBlocks 一致;未闭合则不跳,照渲染降级口径)
    if (/^```/.test(line)) {
      let end = -1
      for (let j = i + 1; j < lines.length; j++) {
        if (/^```\s*$/.test(lines[j])) { end = j; break }
      }
      if (end > i) {
        i = end + 1
        continue
      }
    }
    const h = line.match(/^(#{1,3}) (.+)$/)
    if (h) outline.push({ level: h[1].length, text: h[2].trim(), id: mdHeadingId(ids) })
    i++
  }
  return outline
}
