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
import { renderMarkdown } from '@/utils/markdown'
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

// ---- Markdown render:统一走共享渲染器(ul/ol/表格/引用块/链接全能力),排版由 globals.css `.md` 承接 ----


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
                      className="md prose prose-sm max-w-none text-text"
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
