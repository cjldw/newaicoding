/**
 * KnowledgeBaseView — R20 知识库阅读/编辑页
 * - /projects/:projectId/knowledge-bases/:kbId
 * - 面包屑 + 同步徽章 + "重新导入"按钮
 * - 搜索(300ms 防抖)
 * - 左树(260px,可折叠) + 右内容(max-w-[860px])
 * - Markdown 渲染 / 编辑(CodeEditor + 标题)
 * - 未保存离开提示
 * - importing 状态 3s 轮询
 */
import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import CodeEditor from '@/components/Editor'
import { Loader2, ChevronRight, ChevronDown, RefreshCw } from 'lucide-react'
import {
  useKnowledgeBaseDetail,
  useDocs,
  useDocDetail,
  useSyncKnowledgeBase,
  useCreateDoc,
  usePutDoc,
  useDeleteDoc,
  useSearchDocs,
  type KnowledgeDoc,
} from '@/api/knowledgeBases'

// ---- Tree helpers ----
interface TreeNode {
  id: string
  title: string
  path: string
  docId?: string
  children: TreeNode[]
}

function buildTree(docs: Omit<KnowledgeDoc, 'content'>[]): TreeNode[] {
  const root: TreeNode[] = []
  const map = new Map<string, TreeNode>()
  const sorted = [...docs].sort((a, b) => a.path.localeCompare(b.path))
  for (const d of sorted) {
    const node: TreeNode = { id: d.doc_id, title: d.title, path: d.path, docId: d.doc_id, children: [] }
    map.set(d.path, node)
  }
  for (const d of sorted) {
    const node = map.get(d.path)!
    const parentPath = d.path.includes('/') ? d.path.slice(0, d.path.lastIndexOf('/')) : ''
    if (parentPath && map.has(parentPath)) {
      map.get(parentPath)!.children.push(node)
    } else {
      root.push(node)
    }
  }
  return root
}

function TreeNodes({
  nodes, expanded, onToggle, selectedDocId, onSelect, depth = 0,
}: {
  nodes: TreeNode[]
  expanded: Set<string>
  onToggle: (id: string) => void
  selectedDocId: string | null
  onSelect: (docId: string) => void
  depth?: number
}) {
  return (
    <>
      {nodes.map((n) => {
        const hasChildren = n.children.length > 0
        const isExpanded = expanded.has(n.id)
        const isSelected = n.docId === selectedDocId
        return (
          <div key={n.id}>
            <div
              className={`flex items-center gap-1 px-2 py-1.5 text-sm cursor-pointer rounded transition-colors ${
                isSelected ? 'bg-primary/10 text-primary' : 'hover:bg-surface-strong text-text'
              }`}
              style={{ paddingLeft: `${depth * 12 + 8}px` }}
              onClick={() => n.docId ? onSelect(n.docId) : onToggle(n.id)}
            >
              {hasChildren ? (
                <button
                  onClick={(e) => { e.stopPropagation(); onToggle(n.id) }}
                  className="text-text-muted hover:text-text"
                >
                  {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                </button>
              ) : <span className="w-3.5" />}
              <span className="line-clamp-1">{n.title}</span>
            </div>
            {hasChildren && isExpanded && (
              <TreeNodes
                nodes={n.children} expanded={expanded} onToggle={onToggle}
                selectedDocId={selectedDocId} onSelect={onSelect} depth={depth + 1}
              />
            )}
          </div>
        )
      })}
    </>
  )
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}

// ---- Markdown render (simple 本地版;R2.F4 扩展:行内链接/有序列表 <ol> 包裹/引用块/表格) ----
// 口径:转义优先(&<> 先转义再替换,无 XSS 面);链接仅放行 http/https/相对路径
// (javascript:/data: 等带 scheme 的降级为纯文本);有序/无序列表用真实 <ul>/<ol>
// 包裹(修裸 <li> 编号串号);非 md 内容按纯文本段落渲染,维持原文可读。不引外部库。
function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** 仅放行 http(s):// 与相对路径(/、./、../、# 或无 scheme 的裸路径) */
function isSafeHref(url: string): boolean {
  return /^(https?:\/\/|\/|\.\.?\/|#)/i.test(url) || !/^[a-z][a-z0-9+.-]*:/i.test(url)
}

/** 行内语法:转义 → 行内代码 → 加粗 → 斜体 → 链接 */
function renderInline(seg: string): string {
  let s = escapeHtml(seg)
  s = s.replace(/`([^`]+)`/g, '<code class="bg-surface-strong px-1 rounded">$1</code>')
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (raw, text: string, url: string) => {
    if (!isSafeHref(url)) return raw
    const href = url.replace(/"/g, '%22').replace(/'/g, '%27')
    const external = /^https?:\/\//i.test(url)
    return `<a class="text-primary underline underline-offset-2 break-all" href="${href}"${external ? ' target="_blank" rel="noopener noreferrer"' : ''}>${text}</a>`
  })
  return s
}

/** 表格分隔行:| --- | :---: | 形态(每格仅由 -: 与空格构成) */
function isTableSep(line: string): boolean {
  const t = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return t.length > 0 && t.split('|').every((c) => /^ *:?-+:? *$/.test(c))
}

function renderMarkdown(content: string): string {
  const lines = content.replace(/\r\n?/g, '\n').split('\n')
  const out: string[] = []
  let para: string[] = []
  const flushPara = () => {
    if (para.length) {
      out.push(`<p class="my-2">${para.map(renderInline).join('<br/>')}</p>`)
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
        out.push(`<pre class="bg-surface-strong p-3 rounded my-2 overflow-x-auto"><code>${escapeHtml(lines.slice(i + 1, end).join('\n'))}</code></pre>`)
        i = end + 1
        continue
      }
    }
    // 标题
    const h = line.match(/^(#{1,3}) (.+)$/)
    if (h) {
      flushPara()
      const level = h[1].length
      const cls = ['text-2xl font-bold mt-6 mb-3', 'text-xl font-semibold mt-5 mb-2', 'text-lg font-semibold mt-4 mb-2'][level - 1]
      out.push(`<h${level} class="${cls}">${renderInline(h[2])}</h${level}>`)
      i++
      continue
    }
    // 引用块(连续 > 行;内部递归按块渲染)
    if (/^> ?/.test(line)) {
      flushPara()
      const buf: string[] = []
      while (i < lines.length && /^> ?/.test(lines[i])) {
        buf.push(lines[i].replace(/^> ?/, ''))
        i++
      }
      out.push(`<blockquote class="border-l-4 border-border-strong pl-3 my-2 text-text-muted">${renderMarkdown(buf.join('\n'))}</blockquote>`)
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
        `<table class="w-full my-2 text-sm border-collapse">`
        + `<thead><tr>${head.map((c) => `<th class="border border-border px-2.5 py-1.5 text-left font-semibold bg-surface-strong">${c}</th>`).join('')}</tr></thead>`
        + `<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td class="border border-border px-2.5 py-1.5 align-top">${c}</td>`).join('')}</tr>`).join('')}</tbody>`
        + `</table>`,
      )
      continue
    }
    // 无序列表(真实 <ul> 包裹)
    if (/^- /.test(line)) {
      flushPara()
      const items: string[] = []
      while (i < lines.length && /^- /.test(lines[i])) {
        items.push(`<li>${renderInline(lines[i].slice(2))}</li>`)
        i++
      }
      out.push(`<ul class="my-2 pl-6 list-disc space-y-0.5">${items.join('')}</ul>`)
      continue
    }
    // 有序列表(真实 <ol> 包裹,编号由 ol 生成 —— 修裸 <li> 编号串号)
    if (/^\d+\. /.test(line)) {
      flushPara()
      const items: string[] = []
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(`<li>${renderInline(lines[i].replace(/^\d+\. /, ''))}</li>`)
        i++
      }
      out.push(`<ol class="my-2 pl-6 list-decimal space-y-0.5">${items.join('')}</ol>`)
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


// ---- Component ----
export default function KnowledgeBaseView() {
  const { projectId = '', kbId = '' } = useParams()
  const nav = useNavigate()
  const detailQ = useKnowledgeBaseDetail(projectId, kbId)
  const docsQ = useDocs(kbId)
  const syncMut = useSyncKnowledgeBase(projectId, kbId)
  const createDocMut = useCreateDoc(kbId)
  const putDocMut = usePutDoc(kbId)
  const deleteDocMut = useDeleteDoc(kbId)

  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [editTitle, setEditTitle] = useState('')
  const [hasUnsaved, setHasUnsaved] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(t)
  }, [q])

  const docDetailQ = useDocDetail(kbId, selectedDocId ?? '')
  const searchQ = useSearchDocs(kbId, debouncedQ)

  // Polling during import
  useEffect(() => {
    if (detailQ.data?.import_status !== 'importing') return
    const id = setInterval(() => detailQ.refetch(), 3000)
    return () => clearInterval(id)
  }, [detailQ.data?.import_status, detailQ])

  // Auto-select first doc
  useEffect(() => {
    if (!selectedDocId && docsQ.data?.items.length) {
      setSelectedDocId(docsQ.data.items[0].doc_id)
    }
  }, [docsQ.data, selectedDocId])

  // Reset edit state on doc change
  useEffect(() => {
    setIsEditing(false)
    setHasUnsaved(false)
  }, [selectedDocId])

  const tree = useMemo(() => buildTree(docsQ.data?.items ?? []), [docsQ.data])

  const handleSync = () => syncMut.mutate()
  const handleToggle = (id: string) => {
    const next = new Set(expanded)
    next.has(id) ? next.delete(id) : next.add(id)
    setExpanded(next)
  }
  const handleSelect = (docId: string) => {
    if (hasUnsaved && !confirm('有未保存修改,确定离开吗?')) return
    setSelectedDocId(docId)
  }
  const handleEdit = () => {
    setEditContent(docDetailQ.data?.content ?? '')
    setEditTitle(docDetailQ.data?.title ?? '')
    setIsEditing(true)
    setHasUnsaved(false)
  }
  const handleSave = () => {
    if (!selectedDocId) return
    putDocMut.mutate(
      { docId: selectedDocId, title: editTitle, content: editContent },
      { onSuccess: () => { setHasUnsaved(false); setIsEditing(false) } },
    )
  }
  const handleAddDoc = () => {
    const title = prompt('新页面标题')
    if (title?.trim()) createDocMut.mutate({ title: title.trim() })
  }
  const handleDeleteDoc = () => {
    if (!selectedDocId) return
    if (!confirm('确定删除此页面?')) return
    deleteDocMut.mutate(selectedDocId, { onSuccess: () => setSelectedDocId(null) })
  }
  const handleLeave = () => {
    if (hasUnsaved && !confirm('有未保存修改,确定离开吗?')) return
    nav(`/projects/${projectId}/knowledge-bases`)
  }

  const kb = detailQ.data
  const docs = docsQ.data?.items ?? []
  const currentDoc = docDetailQ.data
  const searchItems = searchQ.data?.items ?? []

  if (detailQ.isLoading) {
    return <div className="flex items-center justify-center py-16 text-text-muted">加载中...</div>
  }
  if (!kb) {
    return <div className="flex items-center justify-center py-16 text-text-muted">知识库不存在</div>
  }

  const isImporting = kb.import_status === 'importing'
  const isReadOnly = kb.source_type === 'repo_import'

  return (
    <div className="flex flex-col h-full">
      {/* Header: breadcrumb + actions */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 text-sm">
          <button onClick={handleLeave} className="text-text-muted hover:text-primary">
            知识库
          </button>
          <ChevronRight className="w-3.5 h-3.5 text-text-muted" />
          <span className="text-text font-medium">{kb.name}</span>
          {kb.import_status === 'importing' && (
            <Badge variant="warning"><Loader2 className="w-3 h-3 mr-1 animate-spin" />导入中</Badge>
          )}
          {kb.import_status === 'done' && <Badge variant="success">已同步</Badge>}
          {kb.import_status === 'failed' && <Badge variant="error">导入失败</Badge>}
          {kb.last_synced_at && (
            <span className="text-text-muted text-xs">最后同步: {formatTime(kb.last_synced_at)}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {kb.source_type === 'repo_import' && (
            <Button variant="outline" size="sm" onClick={handleSync} disabled={syncMut.isPending || isImporting}>
              {syncMut.isPending ? '导入中...' : '重新导入'}
              <RefreshCw className={`w-3.5 h-3.5 ml-1 ${isImporting ? 'animate-spin' : ''}`} />
            </Button>
          )}
        </div>
      </div>

      {/* Body: search + tree + content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: search + tree */}
        <div className="w-[260px] border-r border-border flex flex-col">
          <div className="p-3 border-b border-border">
            <Input
              placeholder="搜索页面..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="text-sm"
            />
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {debouncedQ ? (
              searchItems.length ? (
                <div className="flex flex-col gap-1">
                  {searchItems.map((item) => (
                    <div
                      key={item.doc_id}
                      className={`px-2 py-1.5 text-sm rounded cursor-pointer transition-colors ${
                        item.doc_id === selectedDocId ? 'bg-primary/10 text-primary' : 'hover:bg-surface-strong'
                      }`}
                      onClick={() => handleSelect(item.doc_id)}
                    >
                      <div className="font-medium line-clamp-1">{item.title}</div>
                      <div
                        className="text-xs text-text-muted line-clamp-2 mt-0.5"
                        dangerouslySetInnerHTML={{ __html: item.snippet }}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-text-muted text-sm py-8">无匹配结果</div>
              )
            ) : tree.length ? (
              <TreeNodes
                nodes={tree} expanded={expanded} onToggle={handleToggle}
                selectedDocId={selectedDocId} onSelect={handleSelect}
              />
            ) : (
              <div className="text-center text-text-muted text-sm py-8">暂无页面</div>
            )}
          </div>
          {!isReadOnly && (
            <div className="p-3 border-t border-border">
              <Button variant="outline" size="sm" className="w-full" onClick={handleAddDoc}>
                新建页面
              </Button>
            </div>
          )}
        </div>

        {/* Right: content */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-[860px] mx-auto p-6">
            {currentDoc ? (
              <>
                {isEditing ? (
                  <div className="flex flex-col gap-4">
                    <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} className="text-xl font-semibold" />
                    <CodeEditor
                      value={editContent}
                      onChange={(v) => { setEditContent(v ?? ''); setHasUnsaved(true) }}
                      language="markdown"
                    />
                    <div className="flex items-center gap-2 justify-end">
                      {hasUnsaved && <span className="text-sm text-warning">有未保存修改</span>}
                      <Button variant="outline" onClick={() => { setIsEditing(false); setHasUnsaved(false) }}>
                        取消
                      </Button>
                      <Button variant="primary" onClick={handleSave} disabled={putDocMut.isPending}>
                        {putDocMut.isPending ? '保存中...' : '保存'}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start justify-between gap-4 mb-4">
                      <h1 className="text-2xl font-semibold text-text">{currentDoc.title}</h1>
                      {!isReadOnly && (
                        <div className="flex items-center gap-2">
                          <Button variant="outline" size="sm" onClick={handleEdit}>编辑</Button>
                          <Button variant="outline" size="sm" onClick={handleDeleteDoc}>删除</Button>
                        </div>
                      )}
                    </div>
                    <div
                      className="prose prose-sm max-w-none text-text"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(currentDoc.content ?? '') }}
                    />
                    {currentDoc.source_file_path && (
                      <div className="text-xs text-text-muted mt-6 pt-4 border-t border-border">
                        来源: {currentDoc.source_file_path}
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <div className="flex items-center justify-center py-16 text-text-muted">
                {docs.length ? '请选择一个页面' : '暂无页面,请在左侧新建'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
