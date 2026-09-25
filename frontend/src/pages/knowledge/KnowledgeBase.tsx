/**
 * KnowledgeBase — 知识库页
 * - /projects/:projectId/knowledge(项目级,带 Tab 切换 项目知识库 / 平台知识库)
 * - /knowledge(平台级,无 Tab,标题"知识条目",对齐 vp L1544:icon + 标题 + 说明)
 * 工具栏:搜索(300ms 防抖)+ 类型筛选 + "新建条目"
 * 卡片网格:xl=3 / md=2 / sm=1,每张卡=类型徽章+标题+前 100 字+标签+状态徽章+创建时间
 * 分页 + 新建条目 Dialog
 */
import { useState, useMemo, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import {
  Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription,
} from '@/components/ui/Dialog'
import {
  useProjectKnowledge,
  usePlatformKnowledge,
  useCreateProjectKnowledge,
  type KnowledgeType,
  type KnowledgeStatus,
  type KnowledgeEntry,
  type KnowledgeListParams,
} from '@/api/knowledge'

// 类型徽章映射
const typeBadgeMap: Record<KnowledgeType, { label: string; variant: 'primary' | 'secondary' | 'error' | 'outline' }> = {
  code_snippet: { label: '代码片段', variant: 'primary' },
  pattern: { label: '通用模式', variant: 'secondary' },
  pitfall: { label: '踩坑', variant: 'error' },
  doc: { label: '文档', variant: 'outline' },
}

// 状态徽章映射
const statusBadgeMap: Record<KnowledgeStatus, { label: string; variant: 'outline' | 'success' }> = {
  draft: { label: '草稿', variant: 'outline' },
  published: { label: '已发布', variant: 'success' },
}

const typeOptions = [
  { label: '全部类型', value: '' },
  { label: '代码片段', value: 'code_snippet' },
  { label: '通用模式', value: 'pattern' },
  { label: '踩坑', value: 'pitfall' },
  { label: '文档', value: 'doc' },
]

const newEntryTypeOptions = [
  { label: '代码片段', value: 'code_snippet' },
  { label: '通用模式', value: 'pattern' },
  { label: '踩坑', value: 'pitfall' },
  { label: '文档', value: 'doc' },
]

const PAGE_SIZE = 12

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString('zh-CN')
}

function truncate(s: string, n: number): string {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '...' : s
}

type TabKey = 'project' | 'platform'

export default function KnowledgeBase() {
  const { projectId } = useParams<{ projectId: string }>()
  const nav = useNavigate()
  const isProjectScope = !!projectId

  // Tab(仅项目级显示)
  const [tab, setTab] = useState<TabKey>('project')

  // 列表参数(搜索 / 类型 / 页码)
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [typeFilter, setTypeFilter] = useState<KnowledgeType | ''>('')
  const [page, setPage] = useState(1)

  // 300ms 防抖
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(t)
  }, [q])

  // 切换 tab / 筛选时重置页码
  useEffect(() => { setPage(1) }, [tab, debouncedQ, typeFilter])

  const params: KnowledgeListParams = useMemo(() => ({
    q: debouncedQ || undefined,
    type: typeFilter || undefined,
    page,
    page_size: PAGE_SIZE,
  }), [debouncedQ, typeFilter, page])

  const projectQ = useProjectKnowledge(projectId ?? '', params)
  const platformQ = usePlatformKnowledge(params)
  const activeQ = isProjectScope
    ? (tab === 'project' ? projectQ : platformQ)
    : platformQ

  const items = activeQ.data?.items ?? []
  const total = activeQ.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // 新建条目
  const [showCreate, setShowCreate] = useState(false)
  const [newType, setNewType] = useState<KnowledgeType>('code_snippet')
  const [newTitle, setNewTitle] = useState('')
  const [newContent, setNewContent] = useState('')
  const [newTags, setNewTags] = useState('')
  const createMut = useCreateProjectKnowledge(projectId ?? '')

  const openCreate = () => {
    setNewType('code_snippet')
    setNewTitle('')
    setNewContent('')
    setNewTags('')
    setShowCreate(true)
  }

  const handleCreate = () => {
    if (!projectId || !newTitle.trim()) return
    const tags = newTags.split(',').map((t) => t.trim()).filter(Boolean)
    createMut.mutate(
      { type: newType, title: newTitle.trim(), content: newContent, tags },
      { onSuccess: () => setShowCreate(false) },
    )
  }

  const title = isProjectScope
    ? (tab === 'project' ? '项目知识库' : '平台知识库')
    : '知识条目'

  return (
    <div className="page wide">
      {/* 页面标题(vp:icon + 标题 + 换行 + 说明;仅全局 /knowledge 生效,项目空间保持原结构) */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2">
            {!isProjectScope && <BookOpen size={18} />}
            {title}
          </h1>
          {!isProjectScope && (
            <div className="sub">需求归档时 AI 自动提取的可复用知识(条目级,R14);与项目内「知识库」(文档空间 wiki,R20)并存、命名隔离</div>
          )}
        </div>
        {isProjectScope && (
          <div className="acts">
            <Button variant="primary" onClick={openCreate}>
              新建条目
            </Button>
          </div>
        )}
      </div>

      {/* Tab(仅项目级) */}
      {isProjectScope && (
        <div className="tabs">
          {(['project', 'platform'] as TabKey[]).map((k) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`tab${tab === k ? ' active' : ''}`}
            >
              {k === 'project' ? '项目知识库' : '平台知识库'}
            </button>
          ))}
        </div>
      )}

      {/* 工具栏 */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <Input
          placeholder="搜索知识条目..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1 min-w-[220px] max-w-[360px]"
        />
        <Select
          options={typeOptions}
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as KnowledgeType | '')}
          className="w-[140px]"
        />
      </div>

      {/* 卡片网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {items.map((entry: KnowledgeEntry) => {
          const tb = typeBadgeMap[entry.type] ?? typeBadgeMap.doc
          const sb = statusBadgeMap[entry.status] ?? statusBadgeMap.draft
          return (
            <Card
              key={entry.entry_id}
              className="card p-4 flex flex-col gap-2 hover:border-primary transition-colors cursor-pointer"
              /* R2:卡片点击进详情(项目级/平台级按 entry.project_id 选路由) */
              onClick={() => nav(entry.project_id
                ? `/projects/${entry.project_id}/knowledge/${entry.entry_id}`
                : `/knowledge/${entry.entry_id}`)}
            >
              <div className="flex items-center justify-between">
                <Badge variant={tb.variant}>{tb.label}</Badge>
                <Badge variant={sb.variant}>{sb.label}</Badge>
              </div>
              <div className="text-base font-semibold text-text line-clamp-1">
                {entry.title}
              </div>
              <div className="text-sm text-text-muted line-clamp-3">
                {truncate(entry.content, 100)}
              </div>
              <div className="flex flex-wrap gap-1">
                {(entry.tags ?? []).slice(0, 5).map((tag, i) => (
                  <Badge key={i} variant="default">{tag}</Badge>
                ))}
              </div>
              <div className="text-xs text-text-muted mt-auto">
                {formatTime(entry.created_at)}
              </div>
            </Card>
          )
        })}
        {!activeQ.isLoading && items.length === 0 && (
          <div className="col-span-full text-center text-text-muted py-16">
            暂无知识条目
          </div>
        )}
        {activeQ.isLoading && (
          <div className="col-span-full text-center text-text-muted py-16">
            加载中...
          </div>
        )}
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            上一页
          </Button>
          <span className="text-sm text-text-muted">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            下一页
          </Button>
        </div>
      )}

      {/* 新建条目 Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建知识条目</DialogTitle>
            <DialogDescription>在项目知识库中创建一条新知识</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3 py-3">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text">类型</label>
              <Select
                options={newEntryTypeOptions}
                value={newType}
                onChange={(e) => setNewType(e.target.value as KnowledgeType)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text">标题</label>
              <Input
                placeholder="请输入标题"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text">内容</label>
              <Textarea
                placeholder="请输入内容"
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                rows={5}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text">标签</label>
              <Input
                placeholder="多个标签用英文逗号分隔"
                value={newTags}
                onChange={(e) => setNewTags(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowCreate(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={!newTitle.trim() || createMut.isPending}
            >
              {createMut.isPending ? '创建中...' : '创建'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
