/**
 * KnowledgeBase — 知识库页
 * - /projects/:projectId/knowledge(项目级,带 Tab 切换 项目知识库 / 平台知识库)
 * - /knowledge(平台级,无 Tab,标题"知识条目",对齐 vp L1544:icon + 标题 + 说明)
 * 工具栏:搜索(300ms 防抖)+ 类型筛选 + "新建条目"
 * 卡片网格:xl=3 / md=2 / sm=1,每张卡=类型徽章+标题+摘要行(R4:接口 summary;A 型无 content 显示「关联代码 · n 个路径」占位,否则不显示)+标签+状态徽章+创建时间
 * 分页 + 新建条目 Dialog(R1 双类型:直接创建 | 关联代码)
 */
import { useState, useMemo, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { AlertCircle, BookOpen, Plus, X } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import {
  Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription,
} from '@/components/ui/Dialog'
import { useToast } from '@/hooks/useToast'
import { ApiError } from '@/api/client'
import { useProjectDetail, useProjectRepoBranches, useProjectList } from '@/api/projects'
import { renderMarkdown } from '@/utils/markdown'
import {
  useProjectKnowledge,
  usePlatformKnowledge,
  useCreateProjectKnowledge,
  isCodeSource,
  type KnowledgeType,
  type KnowledgeStatus,
  type KnowledgeEntry,
  type KnowledgeListParams,
  type CreateKnowledgePayload,
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

// ---- R1:新建条目双类型(直接创建 | 关联代码) ----
type CreateMode = 'direct' | 'code'
const createModeLabel: Record<CreateMode, string> = {
  direct: '直接创建',
  code: '关联代码',
}

// 仓库角色标注(与 RepoManagement.tsx roleMap 同文案)
const repoRoleLabel: Record<string, string> = {
  main: '主仓库', test: '测试', docs: '文档', other: '其他',
}

/** gitlab repo url → group/repo 短名(下拉展示用) */
function repoShortName(url: string): string {
  const seg = url.replace(/\/+$/, '').replace(/\.git$/, '').split('/')
  return seg.length >= 2 ? seg.slice(-2).join('/') : url
}

/** 创建失败提示:20010/20011 服务端错误码接住显示,其余透传 message(文案照分片) */
function createErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 20010) return '路径最多 10 个'
    if (e.code === 20011) return '该仓库不属于本项目'
    return e.message
  }
  return e instanceof Error ? e.message : '创建失败'
}

const PATHS_LIMIT = 10

const PAGE_SIZE = 12

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString('zh-CN')
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

  // ---- 新建条目(R1 双类型 Dialog) ----
  const [, showToast, ToastEl] = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [mode, setMode] = useState<CreateMode>('direct')
  const [newType, setNewType] = useState<KnowledgeType>('code_snippet')
  const [newTitle, setNewTitle] = useState('')
  const [newContent, setNewContent] = useState('')
  const [newTags, setNewTags] = useState('')
  // 直接创建 Tab:内容编辑/预览切换
  const [contentPreview, setContentPreview] = useState(false)
  // 关联代码 Tab:说明(与 B 型正文分开,避免长文误带成说明)
  const [codeDesc, setCodeDesc] = useState('')
  const [codeRepoId, setCodeRepoId] = useState('')
  const [codeBranch, setCodeBranch] = useState('')
  const [codePaths, setCodePaths] = useState<string[]>([''])
  const [createErr, setCreateErr] = useState<string | null>(null)
  // 平台级(/knowledge)创建:先选归属项目,提交到该项目知识库;项目级即当前项目
  const [targetProjectId, setTargetProjectId] = useState('')
  const targetPid = isProjectScope ? (projectId ?? '') : targetProjectId
  const qc = useQueryClient()
  const createMut = useCreateProjectKnowledge(targetPid)

  // 归属项目下拉(平台级):项目列表接口按当前用户成员关系返回
  const { data: projectsData } = useProjectList({ status: 'active', page: 1, page_size: 100 })
  const projectOptions = useMemo(() => (projectsData?.items ?? []).map((p) => ({
    value: p.project_id,
    label: p.name,
  })), [projectsData])

  // 项目绑定仓库(仓库下拉数据源,参照 RepoManagement;平台级跟随所选归属项目)
  const { data: project } = useProjectDetail(targetPid)
  const repoOptions = useMemo(() => (project?.repos ?? []).map((r) => ({
    value: r.repo_id,
    label: `${repoShortName(r.gitlab_repo_url)}（${repoRoleLabel[r.role] ?? '其他'}）`,
  })), [project])

  // 分支下拉:选仓库后加载;default 分支置顶并标注(照分片)
  const branchesQ = useProjectRepoBranches(targetPid, codeRepoId)
  const branchOptions = useMemo(() => {
    const list = [...(branchesQ.data ?? [])].sort((a, b) => Number(b.default) - Number(a.default))
    return list.map((b) => ({ value: b.name, label: b.default ? `${b.name}（默认）` : b.name }))
  }, [branchesQ.data])
  // 分支加载完成:当前值失效(或为空)时自动选中 default 分支,避免空值提交
  useEffect(() => {
    const list = branchesQ.data
    if (!list || list.length === 0) return
    setCodeBranch((cur) => (
      cur && list.some((b) => b.name === cur) ? cur : (list.find((b) => b.default) ?? list[0]).name
    ))
  }, [branchesQ.data])

  // 非空路径数(提交时剔除空行;上限 10)
  const validCodePaths = useMemo(
    () => codePaths.map((p) => p.trim()).filter(Boolean),
    [codePaths],
  )

  const openCreate = () => {
    setMode('direct')
    setNewType('code_snippet')
    setNewTitle('')
    setNewContent('')
    setNewTags('')
    setContentPreview(false)
    setCodeDesc('')
    setCodeRepoId('')
    setCodeBranch('')
    setCodePaths([''])
    setCreateErr(null)
    setTargetProjectId('')
    setShowCreate(true)
  }

  const handleCreate = () => {
    if (!targetPid || !newTitle.trim() || createMut.isPending) return
    if (mode === 'code' && !codeRepoId) {
      setCreateErr('请先选择仓库')
      return
    }
    const tags = newTags.split(',').map((t) => t.trim()).filter(Boolean)
    const payload: CreateKnowledgePayload = {
      type: newType,
      title: newTitle.trim(),
      content: mode === 'code' ? codeDesc : newContent,
      tags,
    }
    // A 型:组装 source_links(空行已剔除);B 型:不传
    if (mode === 'code') {
      payload.source_links = [{
        type: 'code', repo_id: codeRepoId, branch: codeBranch, paths: validCodePaths,
      }]
    }
    createMut.mutate(payload, {
      onSuccess: () => {
        setShowCreate(false)
        if (isProjectScope) {
          showToast('ok', '已创建')
        } else {
          // 平台级:归属项目刚创建的条目不会立刻出现在平台列表,主动失效重取
          qc.invalidateQueries({ queryKey: ['platform-knowledge'] })
          const pname = projectsData?.items.find((p) => p.project_id === targetPid)?.name
            ?? '所选项目'
          showToast('ok', `已创建到项目「${pname}」知识库;平台级条目由项目 owner 提升产生`)
        }
      },
      onError: (e) => setCreateErr(createErrorMessage(e)),
    })
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
        <div className="acts">
          <Button variant="primary" onClick={openCreate}>
            <Plus className="w-4 h-4 mr-1" />
            新建条目
          </Button>
        </div>
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
          // R4:摘要读接口 summary(后端截前 100 字);为空且 A 型(source_links 含 code 对象)
          // 显示「关联代码 · n 个路径」占位,否则不显示摘要行
          const codeSource = entry.source_links?.find(isCodeSource)
          const summary = entry.summary
            || (codeSource ? `关联代码 · ${codeSource.paths?.length ?? 0} 个路径` : '')
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
              {summary !== '' && (
                <div className="text-sm text-text-muted line-clamp-3">
                  {summary}
                </div>
              )}
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

      {/* 新建条目 Dialog(R1 双类型:顶部 Tab「直接创建 | 关联代码」) */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建知识条目</DialogTitle>
            <DialogDescription>在项目知识库中创建一条新知识</DialogDescription>
          </DialogHeader>
          {/* 双类型 Tab(.tab/.tab.on,与页级 Tab 同体系) */}
          <div className="tabs">
            {(['direct', 'code'] as CreateMode[]).map((m) => (
              <button
                key={m}
                type="button"
                className={`tab${mode === m ? ' on' : ''}`}
                onClick={() => { setMode(m); setCreateErr(null) }}
              >
                {createModeLabel[m]}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-3 py-3">
            {/* 平台级:先选归属项目(项目级固定为当前项目,不显示) */}
            {!isProjectScope && (
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-text">归属项目</label>
                <Select
                  options={projectOptions}
                  value={targetProjectId}
                  placeholder="请选择归属项目"
                  onChange={(e) => { setTargetProjectId(e.target.value); setCodeRepoId(''); setCodeBranch('') }}
                />
              </div>
            )}
            {mode === 'direct' ? (
              <>
                {/* B 型:现状四字段(类型/标题/内容/标签)+ 内容编辑/预览切换 */}
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
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-text">内容</label>
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant={contentPreview ? 'ghost' : 'outline'}
                        onClick={() => setContentPreview(false)}
                      >
                        编辑
                      </Button>
                      <Button
                        size="sm"
                        variant={contentPreview ? 'outline' : 'ghost'}
                        onClick={() => setContentPreview(true)}
                      >
                        预览
                      </Button>
                    </div>
                  </div>
                  {contentPreview ? (
                    <div className="input md min-h-[120px] max-h-[280px] overflow-auto">
                      {newContent.trim() ? (
                        <div dangerouslySetInnerHTML={{ __html: renderMarkdown(newContent) }} />
                      ) : (
                        <span className="text-text-muted">暂无内容</span>
                      )}
                    </div>
                  ) : (
                    <Textarea
                      placeholder="请输入内容"
                      value={newContent}
                      onChange={(e) => setNewContent(e.target.value)}
                      rows={5}
                    />
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">标签</label>
                  <Input
                    placeholder="多个标签用英文逗号分隔"
                    value={newTags}
                    onChange={(e) => setNewTags(e.target.value)}
                  />
                </div>
              </>
            ) : (
              <>
                {/* A 型:标题/类型(默认 code_snippet)/标签/说明 + 仓库/分支/路径 */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">标题</label>
                  <Input
                    placeholder="请输入标题"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">类型</label>
                  <Select
                    options={newEntryTypeOptions}
                    value={newType}
                    onChange={(e) => setNewType(e.target.value as KnowledgeType)}
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
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">说明</label>
                  <Textarea
                    placeholder="为什么这段代码值得沉淀?(Markdown,可选)"
                    value={codeDesc}
                    onChange={(e) => setCodeDesc(e.target.value)}
                    rows={3}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">仓库</label>
                  <Select
                    options={repoOptions}
                    value={codeRepoId}
                    placeholder="请选择仓库"
                    onChange={(e) => { setCodeRepoId(e.target.value); setCodeBranch('') }}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">分支</label>
                  <Select
                    options={branchOptions}
                    value={codeBranch}
                    placeholder={!codeRepoId
                      ? '请先选择仓库'
                      : (branchesQ.isLoading ? '分支加载中...' : undefined)}
                    disabled={!codeRepoId || branchesQ.isLoading}
                    onChange={(e) => setCodeBranch(e.target.value)}
                  />
                  {branchesQ.error && (
                    <div className="text-xs text-red-fg">
                      {branchesQ.error instanceof Error ? branchesQ.error.message : '分支加载失败'}
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">路径</label>
                  <div className="flex flex-col gap-2">
                    {codePaths.map((p, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <Input
                          className="flex-1 font-mono text-[12.5px]"
                          placeholder="如 backend/app/services/"
                          value={p}
                          onChange={(e) => setCodePaths((arr) => arr.map((x, j) => (j === i ? e.target.value : x)))}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={codePaths.length <= 1}
                          title="删除此路径"
                          onClick={() => setCodePaths((arr) => arr.filter((_, j) => j !== i))}
                        >
                          <X size={14} />
                        </Button>
                      </div>
                    ))}
                  </div>
                  <div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={codePaths.length >= PATHS_LIMIT}
                      title={codePaths.length >= PATHS_LIMIT ? '路径最多 10 个' : undefined}
                      onClick={() => setCodePaths((arr) => [...arr, ''])}
                    >
                      <Plus size={13} />添加路径
                    </Button>
                  </div>
                </div>
              </>
            )}
            {/* 创建失败提示(前端校验 + 服务端 20010/20011 接住显示) */}
            {createErr && (
              <div className="flex items-start gap-2 p-3 rounded-md bg-red-bg border border-red-border">
                <AlertCircle className="w-4 h-4 text-red-fg mt-0.5 flex-shrink-0" />
                <p className="text-sm text-red-fg">{createErr}</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowCreate(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={!targetPid || !newTitle.trim() || createMut.isPending
                || (mode === 'code' && validCodePaths.length === 0)}
            >
              {createMut.isPending ? '创建中...' : '创建'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {ToastEl}
    </div>
  )
}
