/**
 * KnowledgeBaseList — R20 知识库列表页
 * - /projects/:projectId/knowledge-bases
 * - 标题"知识库" + "新建知识库"按钮(primary)
 * - 卡片网格:名称/类型徽章/同步徽章/页面数/更新时间
 * - 点击进阅读页;删除图标+确认
 * - 新建知识库对话框:Radio 空模板/目录导入 + 动态表单
 */
import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { RadioGroup } from '@/components/ui/RadioGroup'
import {
  Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription,
} from '@/components/ui/Dialog'
import { Loader2, Trash2, BookOpen } from 'lucide-react'
import {
  useKnowledgeBases,
  useCreateKnowledgeBase,
  useDeleteKnowledgeBase,
  type KnowledgeBase,
  type SourceType,
} from '@/api/knowledgeBases'

const typeBadgeMap: Record<SourceType, { label: string; variant: 'secondary' | 'outline' }> = {
  blank: { label: '空模板', variant: 'secondary' },
  repo_import: { label: '目录导入', variant: 'outline' },
}

function syncBadge(status: KnowledgeBase['import_status']) {
  if (status === 'importing') return { label: '导入中', variant: 'warning' as const, icon: true }
  if (status === 'done') return { label: '已同步', variant: 'success' as const, icon: false }
  if (status === 'failed') return { label: '导入失败', variant: 'error' as const, icon: false }
  return null
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function KnowledgeBaseList() {
  const { projectId = '' } = useParams<{ projectId: string }>()
  const nav = useNavigate()
  const { data, isLoading } = useKnowledgeBases(projectId)
  const createMut = useCreateKnowledgeBase(projectId)
  const deleteMut = useDeleteKnowledgeBase(projectId)

  const [showCreate, setShowCreate] = useState(false)
  const [sourceType, setSourceType] = useState<SourceType>('blank')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [repoId, setRepoId] = useState('')
  const [branch, setBranch] = useState('')
  const [paths, setPaths] = useState<string[]>([''])

  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBase | null>(null)

  const items = data?.items ?? []

  const openCreate = () => {
    setSourceType('blank')
    setName('')
    setDescription('')
    setRepoId('')
    setBranch('')
    setPaths([''])
    setShowCreate(true)
  }

  const handleCreate = () => {
    if (!name.trim()) return
    const payload: any = { name: name.trim(), description: description.trim() || undefined, source_type: sourceType }
    if (sourceType === 'repo_import') {
      payload.source_config = {
        repo_id: repoId,
        branch: branch || undefined,
        paths: paths.filter(Boolean),
      }
    }
    createMut.mutate(payload, { onSuccess: () => setShowCreate(false) })
  }

  const handleDelete = () => {
    if (!deleteTarget) return
    deleteMut.mutate(deleteTarget.kb_id, {
      onSuccess: () => {
        alert('知识库已删除')
        setDeleteTarget(null)
      },
    })
  }

  const addPath = () => setPaths([...paths, ''])
  const removePath = (i: number) => setPaths(paths.filter((_, idx) => idx !== i))
  const updatePath = (i: number, v: string) => setPaths(paths.map((p, idx) => idx === i ? v : p))

  return (
    <div className="page wide">
      {/* 页头 */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><BookOpen size={18} /> 知识库</h1>
          <div className="sub">项目关联的知识库:文档索引与同步管理</div>
        </div>
        <div className="acts">
          <Button variant="primary" onClick={openCreate}>新建知识库</Button>
        </div>
      </div>

      {/* 卡片网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {items.map((kb) => {
          const tb = typeBadgeMap[kb.source_type]
          const sb = syncBadge(kb.import_status)
          return (
            <Card
              key={kb.kb_id}
              className="p-6 flex flex-col gap-3 hover:border-primary transition-colors cursor-pointer"
              onClick={() => nav(`/projects/${projectId}/knowledge-bases/${kb.kb_id}`)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="text-base font-semibold text-text line-clamp-1">{kb.name}</div>
                  {kb.description && (
                    <div className="text-sm text-text-muted line-clamp-2 mt-1">{kb.description}</div>
                  )}
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleteTarget(kb) }}
                  className="text-text-muted hover:text-red-fg transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant={tb.variant}>{tb.label}</Badge>
                {sb && (
                  <Badge variant={sb.variant}>
                    {sb.icon && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
                    {sb.label}
                  </Badge>
                )}
              </div>
              <div className="flex items-center justify-between text-xs text-text-muted mt-auto">
                <span>{kb.docs_count ?? 0} 个页面</span>
                <span>{formatTime(kb.last_synced_at)}</span>
              </div>
            </Card>
          )
        })}
        {!isLoading && items.length === 0 && (
          <div className="col-span-full text-center text-text-muted py-16">暂无知识库</div>
        )}
        {isLoading && (
          <div className="col-span-full text-center text-text-muted py-16">加载中...</div>
        )}
      </div>

      {/* 新建知识库对话框 */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建知识库</DialogTitle>
            <DialogDescription>创建一个新的知识库</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-3">
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-text">类型</label>
              <RadioGroup
                name="sourceType"
                options={[
                  { label: '空模板', value: 'blank' },
                  { label: '目录导入', value: 'repo_import' },
                ]}
                value={sourceType}
                onChange={(v) => setSourceType(v as SourceType)}
              />
              <div className="text-xs text-text-muted">
                {sourceType === 'blank'
                  ? '在平台内创建并编辑页面'
                  : '从仓库目录导入 .md 生成只读快照,可手动同步'}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text">名称</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="请输入名称" />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text">描述(选填)</label>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
            </div>
            {sourceType === 'repo_import' && (
              <>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">仓库</label>
                  <Select
                    options={[{ label: '请选择仓库', value: '' }]}
                    value={repoId}
                    onChange={(e) => setRepoId(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">分支</label>
                  <Input value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="留空使用默认分支" />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">导入目录(可多选)</label>
                  {paths.map((p, i) => (
                    <div key={i} className="flex gap-2">
                      <Input value={p} onChange={(e) => updatePath(i, e.target.value)} placeholder="例:docs/api" />
                      {paths.length > 1 && (
                        <Button variant="outline" size="sm" onClick={() => removePath(i)}>删除</Button>
                      )}
                    </div>
                  ))}
                  <Button variant="outline" size="sm" onClick={addPath}>添加目录</Button>
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowCreate(false)}>取消</Button>
            <Button variant="primary" onClick={handleCreate} disabled={!name.trim() || createMut.isPending}>
              {createMut.isPending ? '创建中...' : '创建'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认对话框 */}
      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除知识库</DialogTitle>
            <DialogDescription>
              确定删除知识库 {deleteTarget?.name} 吗?其下 {deleteTarget?.docs_count ?? 0} 个页面将一并删除,不影响 GitLab 仓库
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>取消</Button>
            <Button variant="danger" onClick={handleDelete} disabled={deleteMut.isPending}>
              {deleteMut.isPending ? '删除中...' : '确定'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
