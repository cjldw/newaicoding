/**
 * EntryDetail — 知识条目详情页(R2;样板轨:globals.css 现有类 + 现有页面写法,无独立设计稿)
 *
 * 双路由共用(参照 knowledge-bases/:kbId 先例,router.tsx):
 * - /projects/:projectId/knowledge/:entryId(项目级)
 * - /knowledge/:entryId(平台级)
 *
 * 区块结构(照分片「页面结构说明」):
 *   .page
 *   ├─ .page-head:←返回 | 类型徽章+标题 | 状态徽章 | .acts(发布/提升/编辑/删除,按权限显示)
 *   ├─ 信息行:创建者(AI/人)·创建时间·标签 chips·source_links 链接
 *   ├─ .card 正文区:.md 渲染 content(无 content 且为 A 型时不显示此卡)
 *   └─ 代码引用区(仅 A 型):标题「关联代码 · {repo} · {branch}」+ 逐路径块
 *      每块:.card 头(路径 mono + 重新拉取按钮)+ 体(monaco 只读 / 目录清单 / 错误占位)
 *
 * 权限:消费详情接口 permissions{can_edit,can_delete,editable_fields}(R3 预埋);
 * 后端未返回 permissions 时容错缺省 —— 发布/提升用项目成员角色兜底(viewer 不见发布,
 * 仅 owner 见提升),编辑/删除仅在后端明确授予时显示。
 * 代码块逐路径懒加载(进入视口才请求,失败互不影响);目录树节点可折叠,文本文件
 * 展开即显示内容(数据随递归响应一次带回,无需二次请求)。
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, ChevronRight, FileCode, FileText,
  GitBranch, Link as LinkIcon, Loader2, RefreshCw,
} from 'lucide-react'
import CodeEditor from '@/components/Editor'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import {
  Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription,
} from '@/components/ui/Dialog'
import { useToast } from '@/hooks/useToast'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useProjectDetail, useProjectMembers } from '@/api/projects'
import { renderMarkdown } from '@/utils/markdown'
import {
  useKnowledgeDetail, useKnowledgeCode, usePublishKnowledge, usePromoteKnowledge,
  isCodeSource,
  type KnowledgeCodeFileNode,
  type KnowledgeEntryDetail,
} from '@/api/knowledge'

// ---- 徽章映射(与列表页 KnowledgeBase 同口径,原值照抄) ----
const typeBadgeMap = {
  code_snippet: { label: '代码片段', variant: 'primary' },
  pattern: { label: '通用模式', variant: 'secondary' },
  pitfall: { label: '踩坑', variant: 'error' },
  doc: { label: '文档', variant: 'outline' },
} as const

const statusBadgeMap = {
  draft: { label: '草稿', variant: 'outline' },
  published: { label: '已发布', variant: 'success' },
} as const

type ProjectRole = 'owner' | 'editor' | 'viewer'

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + '...' : s
}

/** 创建者标注:后端为 ai/human 枚举(历史类型标注为用户对象,双形态容错) */
function createdByLabel(cb: KnowledgeEntryDetail['created_by']): string {
  if (typeof cb === 'string') return cb === 'ai' ? 'AI' : '人'
  return cb?.nickname || cb?.username || '-'
}

/** monaco language 按扩展名推断(编辑器只读高亮) */
const EXT_LANG: Record<string, string> = {
  ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
  mjs: 'javascript', cjs: 'javascript', py: 'python', go: 'go', rs: 'rust',
  java: 'java', kt: 'kotlin', rb: 'ruby', php: 'php', c: 'c', h: 'c',
  cpp: 'cpp', cc: 'cpp', hpp: 'cpp', cs: 'csharp', swift: 'swift',
  md: 'markdown', json: 'json', yaml: 'yaml', yml: 'yaml', toml: 'ini',
  sh: 'shell', bash: 'shell', zsh: 'shell', sql: 'sql', css: 'css',
  scss: 'scss', less: 'less', html: 'html', htm: 'html', vue: 'html', xml: 'xml',
}
function langFromPath(p: string): string {
  const ext = p.split('.').pop()?.toLowerCase() ?? ''
  return EXT_LANG[ext] ?? 'plaintext'
}

function fmtSize(n?: number): string {
  if (typeof n !== 'number' || isNaN(n)) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

/** gitlab repo url → group/repo 展示名(解绑/取不到时回退 repo_id 短位) */
function repoDisplayName(repoId: string, url?: string): string {
  if (url) {
    const seg = url.replace(/\/+$/, '').replace(/\.git$/, '').split('/')
    if (seg.length >= 2) return seg.slice(-2).join('/')
  }
  return repoId.length > 12 ? `${repoId.slice(0, 8)}…` : repoId
}

/** 树中按 path 找节点(目录递归响应一次带回,选中文件直接取 content,不二次请求) */
function findNode(nodes: KnowledgeCodeFileNode[], path: string): KnowledgeCodeFileNode | null {
  for (const n of nodes) {
    if (n.path === path) return n
    if (n.children?.length) {
      const hit = findNode(n.children, path)
      if (hit) return hit
    }
  }
  return null
}

/**
 * 进入视口检测(逐路径懒加载):块滚进视口(预取 120px)才发起 code 请求;
 * IntersectionObserver 不可用时兜底为立即加载。
 */
function useInView<T extends HTMLElement>(): [React.RefObject<T>, boolean] {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(false)
  useEffect(() => {
    if (inView) return
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }
    const el = ref.current
    if (!el) return
    const ob = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true)
          ob.disconnect()
        }
      },
      { rootMargin: '120px' },
    )
    ob.observe(el)
    return () => ob.disconnect()
  }, [inView])
  // 断言收窄:挂载时 ref 已绑定到块根元素(current 为 null 仅在首帧前)
  return [ref as React.RefObject<T>, inView]
}

/** 目录树节点(复用 .tree/.tnode 类 + TaskDetail 层级缩进思路;目录可折叠) */
function DirNode({
  node, depth, selPath, onSelect,
}: {
  node: KnowledgeCodeFileNode
  depth: number
  selPath: string | null
  onSelect: (path: string) => void
}) {
  const [open, setOpen] = useState(depth < 1)
  const isDir = node.kind === 'dir'
  // 二进制容错:后端 binary 标记,或 kind=file 但未带 content(契约:二进制只列节点不拉内容)
  const binary = !isDir && (node.binary === true || typeof node.content !== 'string')
  const name = node.path.split('/').pop() ?? node.path
  return (
    <>
      <div
        className={`tnode click${selPath === node.path ? ' sel' : ''}`}
        style={{ paddingLeft: depth * 14 + 8 }} // 层级缩进为动态值,保留内联
        onClick={() => (isDir ? setOpen((o) => !o) : onSelect(node.path))}
      >
        {isDir ? (
          open ? <ChevronDown size={14} className="ic" /> : <ChevronRight size={14} className="ic" />
        ) : (
          <FileText size={14} className="ic" />
        )}
        <span className="nm mono">{name}</span>
        {!isDir && typeof node.size === 'number' && (
          <span className="small faint nowrap">{fmtSize(node.size)}</span>
        )}
        {binary && <span className="bdg b-zinc bdg-mini">二进制</span>}
      </div>
      {isDir && open && (node.children ?? []).map((c) => (
        <DirNode key={c.path} node={c} depth={depth + 1} selPath={selPath} onSelect={onSelect} />
      ))}
    </>
  )
}

/** 目录块体:树状清单 + 选中文件预览(文本 monaco 只读 / 二进制占位) */
function DirBody({ entryId, tree }: { entryId: string; tree: KnowledgeCodeFileNode[] }) {
  const [selPath, setSelPath] = useState<string | null>(null)
  const sel = selPath ? findNode(tree, selPath) : null
  return (
    <div>
      <div className="overflow-auto" style={{ maxHeight: 320 }}>
        <div className="tree">
          {tree.length === 0 && <div className="empty">无文件</div>}
          {tree.map((n) => (
            <DirNode key={n.path} node={n} depth={0} selPath={selPath} onSelect={setSelPath} />
          ))}
        </div>
      </div>
      {sel && (
        <div className="border-t border-border">
          {typeof sel.content === 'string' ? (
            <div style={{ height: 320 }}>
              <CodeEditor
                value={sel.content}
                language={langFromPath(sel.path)}
                path={`knowledge://${entryId}/${sel.path}`}
                readOnly
              />
            </div>
          ) : (
            <div className="empty">二进制文件,不支持预览</div>
          )}
        </div>
      )}
    </div>
  )
}

/** 逐路径代码块:懒加载 + 独立错误降级 + 重新拉取(穿透缓存) */
function CodePathBlock({
  entryId, path, repoLabel, branch,
}: {
  entryId: string
  path: string
  repoLabel: string
  branch: string
}) {
  const [ref, inView] = useInView<HTMLDivElement>()
  // 重新拉取:nonce 递增 → 换 queryKey 绕缓存,且每次点击都真实重发(refresh=1)
  const [nonce, setNonce] = useState(0)
  const q = useKnowledgeCode(entryId, path, inView, nonce)
  const err = q.error
  // 20012「代码来源不可达」:仓库已解绑 / 分支已删除 / 路径不存在
  const unreachable = err instanceof ApiError && err.code === 20012

  let body = null
  if (!inView || q.isPending) {
    body = <div className="empty">加载中...</div>
  } else if (err) {
    body = unreachable ? (
      <div className="empty">
        <div>代码来源不可达(仓库已解绑或分支已删除)</div>
        <div className="mt-3">
          <Button variant="outline" size="sm" onClick={() => setNonce((n) => n + 1)}>
            <RefreshCw size={13} />重新拉取
          </Button>
        </div>
      </div>
    ) : (
      <div className="empty">
        <button type="button" className="hover:underline" onClick={() => q.refetch()}>
          加载失败,点此重试
        </button>
      </div>
    )
  } else if (q.data) {
    const data = q.data
    body = (
      <>
        {/* 目录截断提示(契约 partial:true,区顶显示;按原因区分文案) */}
        {data.partial && (
          <div className="px-4 pt-3">
            <span className="bdg b-amber">
              {data.partial_reason === 'size'
                ? '目录内容过大,仅部分加载'
                : '目录过大,仅加载前 200 个文件'}
            </span>
          </div>
        )}
        {data.kind === 'dir' ? (
          <DirBody entryId={entryId} tree={data.tree ?? []} />
        ) : typeof data.content === 'string' ? (
          <div style={{ height: 360 }}>
            <CodeEditor
              value={data.content}
              language={langFromPath(path)}
              path={`knowledge://${entryId}/${path}`}
              readOnly
            />
          </div>
        ) : (
          <div className="empty">二进制文件,不支持预览</div>
        )}
      </>
    )
  }

  return (
    <div className="card" ref={ref}>
      <div className="card-head">
        <FileCode size={14} className="text-text-muted flex-none" />
        <span className="mono text-[12.5px] break-all" title={path}>{path}</span>
        <span className="chip"><GitBranch size={12} />{repoLabel} · {branch}</span>
        <div className="right">
          <Button variant="ghost" size="sm" onClick={() => setNonce((n) => n + 1)}>
            <RefreshCw size={13} />重新拉取
          </Button>
        </div>
      </div>
      {body}
    </div>
  )
}

export default function EntryDetail() {
  // 双路由:项目级带 projectId,平台级无(entry.project_id 为准)
  const { entryId = '', projectId = '' } = useParams()
  const nav = useNavigate()
  const [, showToast, ToastEl] = useToast()
  const { user } = useAuthStore()

  const q = useKnowledgeDetail(entryId)
  const entry = q.data

  // 归属项目/成员(角色兜底用;平台级条目 project_id 为空则不启用)
  const { data: project } = useProjectDetail(entry?.project_id ?? '')
  const { data: members } = useProjectMembers(entry?.project_id ?? '')

  // 当前用户在该项目的角色(permissions 未返回时的容错缺省来源)
  const myRole = useMemo<ProjectRole | undefined>(() => {
    if (!entry?.project_id) return undefined
    const me = user?.user_id
    const hit = (members?.items ?? []).find((m) => m.user_id === me)
    if (hit) return hit.role
    if (me && project?.owner?.user_id === me) return 'owner'
    return undefined
  }, [entry?.project_id, members, project, user])

  // ---- 权限消费(R3 预埋 permissions;未返回时按角色缺省) ----
  const perms = entry?.permissions
  const canPublish = !!entry && entry.status === 'draft'
    && (perms ? !!perms.can_edit : myRole === 'owner' || myRole === 'editor')
  const canPromote = !!entry?.project_id && myRole === 'owner'
  const canEdit = perms?.can_edit === true
  const canDelete = perms?.can_delete === true

  const publishMut = usePublishKnowledge(entryId)
  const promoteMut = usePromoteKnowledge(entryId)

  // 确认弹窗(发布/提升共用;确认文案照分片「文案清单」)
  const [confirmMode, setConfirmMode] = useState<null | 'publish' | 'promote'>(null)

  // A 型 = source_links 含 code 对象(R1:含且仅含一个;数组化容错)
  const codeSources = useMemo(
    () => (entry?.source_links ?? []).filter(isCodeSource),
    [entry?.source_links],
  )
  const repoLabelOf = (repoId: string) => {
    const r = project?.repos?.find((x) => x.repo_id === repoId)
    return repoDisplayName(repoId, r?.gitlab_repo_url)
  }

  const goBack = () => {
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0
    if (idx > 0) {
      nav(-1)
      return
    }
    const pid = entry?.project_id || projectId
    nav(pid ? `/projects/${pid}/knowledge` : '/knowledge')
  }

  const handleConfirm = () => {
    if (confirmMode === 'publish') {
      publishMut.mutate(undefined, {
        onSuccess: () => setConfirmMode(null), // 徽章 draft→published、按钮消失(详情失效自动刷新)
        onError: (e) => showToast('err', e instanceof Error ? e.message : '发布失败'),
      })
    } else if (confirmMode === 'promote') {
      promoteMut.mutate(undefined, {
        onSuccess: () => {
          setConfirmMode(null)
          nav('/knowledge') // 提升成功 → 跳转平台库(分片「控件联动」)
        },
        onError: (e) => showToast('err', e instanceof Error ? e.message : '提升失败'),
      })
    }
  }

  // ---- 加载 / 错误态 ----
  if (q.isPending) {
    return (
      <div className="page">
        <div className="page-loading"><Loader2 size={16} className="animate-spin" />加载中...</div>
      </div>
    )
  }
  if (q.error || !entry) {
    // 非成员访问项目级详情 → 403(后端 message 透传);其余错误可点重试
    const msg = q.error instanceof Error && q.error.message ? q.error.message : '加载失败,点此重试'
    return (
      <div className="page">
        <div className="page-head">
          <button className="btn btn-ghost icon-btn" title="返回" onClick={goBack}>
            <ArrowLeft size={15} />
          </button>
        </div>
        <div className="empty">
          <button type="button" className="hover:underline" onClick={() => q.refetch()}>{msg}</button>
        </div>
        {ToastEl}
      </div>
    )
  }

  const tb = typeBadgeMap[entry.type] ?? typeBadgeMap.doc
  const sb = statusBadgeMap[entry.status] ?? statusBadgeMap.draft
  const hasContent = !!entry.content
  // A 型(有关联代码)且无说明文字 → 不显示正文卡(分片「页面结构说明」)
  const showBodyCard = hasContent || codeSources.length === 0
  const tags = entry.tags ?? []

  return (
    <div className="page">
      {/* page-head:返回 | 类型徽章+标题 | 状态徽章 | acts(按权限) */}
      <div className="page-head">
        <button className="btn btn-ghost icon-btn" title="返回" onClick={goBack}>
          <ArrowLeft size={15} />
        </button>
        <h1>
          <Badge variant={tb.variant}>{tb.label}</Badge>
          <span className="break-all">{entry.title}</span>
          <Badge variant={sb.variant}>{sb.label}</Badge>
        </h1>
        <div className="acts">
          {canPublish && (
            <Button variant="primary" size="sm" onClick={() => setConfirmMode('publish')}>
              发布
            </Button>
          )}
          {canPromote && (
            <Button variant="outline" size="sm" onClick={() => setConfirmMode('promote')}>
              提升到平台级
            </Button>
          )}
          {canEdit && (
            <Button
              variant="outline" size="sm"
              onClick={() => showToast('info', '编辑功能即将上线')}
            >
              编辑
            </Button>
          )}
          {canDelete && (
            <Button
              variant="danger" size="sm"
              onClick={() => showToast('info', '删除功能即将上线')}
            >
              删除
            </Button>
          )}
        </div>
      </div>

      {/* 信息行:创建者(AI/人)· 创建时间 · 标签 chips · source_links 链接 */}
      <div className="flex flex-wrap items-center gap-3 mb-5 text-sm text-text-muted">
        <span>创建者:{createdByLabel(entry.created_by)}</span>
        <span>创建时间:{formatTime(entry.created_at)}</span>
        {tags.length > 0 && (
          <span className="flex flex-wrap gap-1">
            {tags.map((tag, i) => (
              <Badge key={i} variant="default">{tag}</Badge>
            ))}
          </span>
        )}
        <span className="flex flex-wrap items-center gap-2">
          {(entry.source_links ?? []).map((l, i) => {
            if (isCodeSource(l)) {
              return (
                <span key={`code-${i}`} className="chip">
                  <GitBranch size={12} />{repoLabelOf(l.repo_id)} · {l.branch}
                </span>
              )
            }
            if (/^https?:\/\//.test(l)) {
              return (
                <a
                  key={`link-${i}`}
                  href={l}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1"
                  title={l}
                >
                  <LinkIcon size={12} />{truncate(l, 48)}
                </a>
              )
            }
            return null
          })}
        </span>
      </div>

      {/* 正文卡:.md 渲染 content(A 型无 content 时不显示) */}
      {showBodyCard && (
        <Card className="p-5 mb-5">
          {hasContent ? (
            <div className="md" dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.content) }} />
          ) : (
            <div className="empty">暂无内容</div>
          )}
        </Card>
      )}

      {/* 代码引用区(仅 A 型):标题「关联代码」+ repo/branch 标注 + 逐路径块 */}
      {codeSources.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="card-title">
            <FileCode size={15} />关联代码
            {codeSources.map((s, i) => (
              <span key={i} className="chip">
                <GitBranch size={12} />{repoLabelOf(s.repo_id)} · {s.branch}
              </span>
            ))}
          </div>
          {codeSources.flatMap((s) => s.paths.map((p) => (
            <CodePathBlock
              key={p}
              entryId={entry.entry_id}
              path={p}
              repoLabel={repoLabelOf(s.repo_id)}
              branch={s.branch}
            />
          )))}
        </div>
      )}

      {/* 发布/提升确认弹窗(确认文案逐字照分片「文案清单」) */}
      <Dialog open={confirmMode !== null} onOpenChange={(o) => { if (!o) setConfirmMode(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmMode === 'publish' ? '发布' : '提升到平台级'}</DialogTitle>
            <DialogDescription>
              {confirmMode === 'publish'
                ? '发布后所有项目成员可见,确认发布?'
                : '提升到平台级后全员可见,且不可撤回,确认?'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmMode(null)}>取消</Button>
            <Button
              variant="primary"
              disabled={publishMut.isPending || promoteMut.isPending}
              onClick={handleConfirm}
            >
              {confirmMode === 'publish'
                ? (publishMut.isPending ? '发布中...' : '发布')
                : (promoteMut.isPending ? '提升中...' : '提升到平台级')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {ToastEl}
    </div>
  )
}
