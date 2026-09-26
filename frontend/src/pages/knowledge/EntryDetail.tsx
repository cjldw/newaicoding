/**
 * EntryDetail — 知识条目详情页(R2;样板轨:globals.css 现有类 + 现有页面写法,无独立设计稿)
 *
 * 双路由共用(参照 knowledge-bases/:kbId 先例,router.tsx):
 * - /projects/:projectId/knowledge/:entryId(项目级)
 * - /knowledge/:entryId(平台级)
 *
 * 区块结构(照分片「页面结构说明」):
 *   .page.wide(全宽,对齐测试管理等页;rd-ui-sticky,2026-09-26)
 *   ├─ A 型 → 「关联代码」工作台粘性钉屏(.entry-code-dock:position:sticky;
 *   │  top:8px = 视口 58px,顶栏在 .route-scroll 滚动口之外;max-height:100vh-70px。
 *   │  页面本体正常文档流滚动,说明区滚走后标题+树+预览钉在视口内,树/预览各自内滚)。
 *   │  B 型 → 同为文档流随页滚
 *   ├─ .page-head:←返回 | 类型徽章+标题 | 状态徽章 | .acts(发布/提升/编辑/删除,按权限显示)
 *   ├─ 信息行:创建者(AI/人)·创建时间·标签 chips·source_links 链接
 *   ├─ 正文区(B 型,R28.F2 左右模式):大纲 ≥2 条时左 .md-toc 目录(sticky,点击锚点平滑
 *   │  滚动)+ 右正文卡;<2 条退单栏;≤1180px 隐藏目录(A 型不渲染大纲)
 *   ├─ .card 正文区:.md 渲染 content(A 型 = 说明文字,普通文档流全宽放工作台上方,
 *   │  随页滚走;无 content 且为 A 型时不显示此卡)
 *   └─ 代码工作台(仅 A 型,2026-09-25):标题「关联代码」+ 左 .code-tree 文件树
 *      (撑满列高内滚,头部 repo·branch,目录折叠/文件选中高亮)+ 右 .code-preview
 *      (.md → markdown / 代码 → monaco 只读 / 二进制 → 占位;头部路径+来源+重新拉取,
 *      体部撑满列高内滚)。整体由 .entry-code-dock 粘性钉屏(2026-09-26)
 *
 * 权限:消费详情接口 permissions{can_edit,can_delete,editable_fields,can_publish,can_promote}
 * (R3 + R3.F2);后端未返回时容错缺省 —— 发布优先后端 can_publish,缺省回退
 * permissions.can_edit 代理或项目成员角色(viewer 不见发布);提升优先后端 can_promote,
 * 缺省回退本地 owner 判断(后端就绪后超管非成员也全可见);编辑/删除仅在后端明确授予时显示。
 * 编辑照 R1 双类型表单回填
 * (A 型可改代码引用,B 型可改正文);AI 条目按 editable_fields 仅放行 tags,
 * 其余字段 disabled + 提示条。删除为危险按钮确认弹窗,成功回列表。
 * 工作台数据策略(2026-09-25 起,替代逐路径块懒加载):各 source path 进入即拉 code
 * 接口(目录递归树一次带回,文本文件随树带 content,点击零请求);树上无 content 的
 * 节点(二进制/未拉取)选中后按需取;「重新拉取」refresh=1 穿透服务端缓存。
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertCircle, ArrowLeft, ChevronDown, ChevronRight, FileCode, FileText,
  GitBranch, Link as LinkIcon, Loader2, Plus, RefreshCw, X,
} from 'lucide-react'
import CodeEditor from '@/components/Editor'
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
import { useAuthStore } from '@/stores/authStore'
import { useProjectDetail, useProjectMembers, useProjectRepoBranches } from '@/api/projects'
import { extractOutline, renderMarkdown } from '@/utils/markdown'
import {
  useKnowledgeDetail, useKnowledgeCode, usePublishKnowledge, usePromoteKnowledge,
  useUpdateKnowledge, useDeleteKnowledge,
  isCodeSource,
  type KnowledgeCodeFileNode,
  type KnowledgeCodeResponse,
  type KnowledgeCodeSource,
  type KnowledgeEntryDetail,
  type KnowledgeType,
  type UpdateKnowledgePayload,
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

// ---- R3:编辑表单共用常量(与 R1 KnowledgeBase 同口径,原值照抄) ----
const newEntryTypeOptions = [
  { label: '代码片段', value: 'code_snippet' },
  { label: '通用模式', value: 'pattern' },
  { label: '踩坑', value: 'pitfall' },
  { label: '文档', value: 'doc' },
]

// 仓库角色标注(与 RepoManagement.tsx roleMap 同文案)
const repoRoleLabel: Record<string, string> = {
  main: '主仓库', test: '测试', docs: '文档', other: '其他',
}

/** gitlab repo url → group/repo 短名(下拉展示用) */
function repoShortName(url: string): string {
  const seg = url.replace(/\/+$/, '').replace(/\.git$/, '').split('/')
  return seg.length >= 2 ? seg.slice(-2).join('/') : url
}

const PATHS_LIMIT = 10

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

/** 深度优先找第一个可预览文本文件(工作台默认选中用) */
function firstPreviewable(nodes: KnowledgeCodeFileNode[]): KnowledgeCodeFileNode | null {
  for (const n of nodes) {
    if (n.kind === 'file' && typeof n.content === 'string') return n
    if (n.children?.length) {
      const hit = firstPreviewable(n.children)
      if (hit) return hit
    }
  }
  return null
}

/** 工作台单 path 加载态(retry 供树内失败行重试:nonce 递增 → 换 key 且 refresh=1) */
interface CodePathState {
  source: KnowledgeCodeSource
  pending: boolean
  error: unknown
  data: KnowledgeCodeResponse | null
  retry: () => void
}

/** 单 path 加载器:进入工作台即拉(树是主内容,不再做视口懒加载),结果上报父级拼树 */
function CodePathLoader({
  entryId, path, source, onState,
}: {
  entryId: string
  path: string
  source: KnowledgeCodeSource
  onState: (path: string, st: CodePathState) => void
}) {
  const [nonce, setNonce] = useState(0)
  const q = useKnowledgeCode(entryId, path, true, nonce)
  useEffect(() => {
    onState(path, {
      source,
      pending: q.isPending,
      error: q.error,
      data: q.data ?? null,
      retry: () => setNonce((n) => n + 1),
    })
  }, [path, source, onState, q.isPending, q.error, q.data])
  return null
}

/** 工作台树节点:目录点击折叠/展开,文件叶子点击选中(选中态持久高亮,BUG-KB-005 同思路) */
function CodeTreeNode({
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
        title={node.path}
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
        <CodeTreeNode key={c.path} node={c} depth={depth + 1} selPath={selPath} onSelect={onSelect} />
      ))}
    </>
  )
}

/** 预览体:.md 后缀 → markdown 正文(复用共享渲染器);其余按扩展名 monaco 只读 */
function renderPreviewBody(entryId: string, path: string, content: string): ReactNode {
  if (/\.md$/i.test(path)) {
    return (
      <div className="md code-preview-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
    )
  }
  return (
    <div className="code-preview-editor">
      <CodeEditor
        value={content}
        language={langFromPath(path)}
        path={`knowledge://${entryId}/${path}`}
        readOnly
      />
    </div>
  )
}

/**
 * A 型(关联代码)工作台:左 .code-tree 文件树 + 右 .code-preview 文件预览
 * - 树 = 各 source path 的 code 接口递归响应拼装(文本文件随树带 content,点击零请求)
 * - 预览:.md → renderMarkdown;代码 → monaco 只读;二进制/未拉取 → code 接口按需取
 * - 「重新拉取」在预览区头(refresh=1 穿透服务端缓存);默认选中第一个可预览文本文件
 */
function CodeWorkbench({
  entryId, sources, repoLabelOf,
}: {
  entryId: string
  sources: KnowledgeCodeSource[]
  repoLabelOf: (repoId: string) => string
}) {
  const [states, setStates] = useState<Record<string, CodePathState>>({})
  const handleState = useCallback((path: string, st: CodePathState) => {
    setStates((prev) => ({ ...prev, [path]: st }))
  }, [])

  // 各 path 响应 → 树根列表(dir 包一层根节点;file 即叶子;pending/error 行由 states 另行渲染)
  const roots = useMemo<KnowledgeCodeFileNode[]>(() => (
    sources.flatMap((s) => s.paths.map((p) => {
      const st = states[p]
      if (!st?.data) return { path: p, kind: 'dir' as const, children: [] }
      if (st.data.kind === 'dir') {
        return { path: p, kind: 'dir' as const, children: st.data.tree ?? [] }
      }
      return {
        path: p,
        kind: 'file' as const,
        content: st.data.content,
        binary: typeof st.data.content !== 'string' ? true : undefined,
        size: st.data.size,
      }
    }))
  ), [sources, states])

  // 节点路径 → 所属 source(预览区头 repo·branch 标注用)
  const pathSource = useMemo(() => {
    const m: Record<string, KnowledgeCodeSource> = {}
    const walk = (nodes: KnowledgeCodeFileNode[], s: KnowledgeCodeSource) => {
      for (const n of nodes) {
        m[n.path] = s
        if (n.children?.length) walk(n.children, s)
      }
    }
    sources.forEach((s) => s.paths.forEach((p) => {
      m[p] = s
      const tree = states[p]?.data?.tree
      if (tree?.length) walk(tree, s)
    }))
    return m
  }, [sources, states])

  // 选中文件 + 按需拉取:树上无 content(二进制/未拉取)或点过「重新拉取」→ 以拉取结果为准
  const [selPath, setSelPath] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const [refreshedFor, setRefreshedFor] = useState<string | null>(null)
  const selNode = selPath ? findNode(roots, selPath) : null
  const selHasContent = selNode != null && typeof selNode.content === 'string'
  const needFetch = !!selPath && (!selHasContent || refreshedFor === selPath)
  const fetchQ = useKnowledgeCode(entryId, needFetch && selPath ? selPath : '', true, nonce)

  // 引用路径被编辑后(pathsKey 变化)复位选中,重新默认选择
  const pathsKey = sources.map((s) => `${s.repo_id}@${s.branch}:${s.paths.join('|')}`).join(';')
  useEffect(() => {
    setSelPath(null)
    setRefreshedFor(null)
  }, [pathsKey])
  // 默认选中第一个可预览文本文件(树数据到位即选,无需用户手点)
  useEffect(() => {
    if (selPath) return
    const first = firstPreviewable(roots)
    if (first) setSelPath(first.path)
  }, [roots, selPath])

  const selSource = selPath ? pathSource[selPath] : undefined
  const handleRefresh = () => {
    if (!selPath) return
    setRefreshedFor(selPath)
    setNonce((n) => n + 1)
  }

  // 预览体:树上有 content 直接用(零请求);否则看按需拉取结果(20012 同现有降级文案)
  let previewBody: ReactNode
  if (!selPath || !selNode) {
    previewBody = <div className="empty">从左侧选择文件查看预览</div>
  } else if (selHasContent && !needFetch) {
    previewBody = renderPreviewBody(entryId, selPath, selNode.content as string)
  } else if (fetchQ.isPending) {
    previewBody = (
      <div className="empty"><Loader2 size={15} className="animate-spin inline-block" /> 加载中...</div>
    )
  } else if (fetchQ.error) {
    const unreachable = fetchQ.error instanceof ApiError && fetchQ.error.code === 20012
    previewBody = (
      <div className="empty">
        <div>{unreachable ? '代码来源不可达(仓库已解绑或分支已删除)' : '加载失败'}</div>
        <div className="mt-3">
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw size={13} />重试
          </Button>
        </div>
      </div>
    )
  } else if (typeof fetchQ.data?.content === 'string') {
    previewBody = renderPreviewBody(entryId, selPath, fetchQ.data.content)
  } else {
    previewBody = <div className="empty">二进制文件,不支持预览</div>
  }

  return (
    <div className="code-wb">
      {/* 各 source path 加载器(渲染 null,只负责拉取并上报父级拼树) */}
      {sources.map((s) => s.paths.map((p) => (
        <CodePathLoader key={p} entryId={entryId} path={p} source={s} onState={handleState} />
      )))}

      {/* 左栏文件树:头部 repo·branch 标注;目录折叠/展开,文件叶子点击选中 */}
      <aside className="code-tree">
        {sources.map((s, i) => (
          <div className="code-tree-group" key={`${s.repo_id}:${s.branch}:${i}`}>
            <div className="code-tree-head">
              <GitBranch size={12} className="ic" />
              <span className="mono" title={`${repoLabelOf(s.repo_id)} · ${s.branch}`}>
                {repoLabelOf(s.repo_id)} · {s.branch}
              </span>
            </div>
            {s.paths.map((p) => {
              const st = states[p]
              if (!st || st.pending) {
                return (
                  <div key={p} className="tnode" title={p}>
                    <Loader2 size={14} className="ic animate-spin" />
                    <span className="nm mono">{p.split('/').filter(Boolean).pop() ?? p}</span>
                  </div>
                )
              }
              if (st.error) {
                const unreachable = st.error instanceof ApiError && st.error.code === 20012
                return (
                  <div
                    key={p}
                    className="tnode"
                    title={unreachable ? '代码来源不可达(仓库已解绑或分支已删除)' : '加载失败'}
                  >
                    <AlertCircle size={14} className="ic t-err" />
                    <span className="nm mono">{p.split('/').filter(Boolean).pop() ?? p}</span>
                    <button type="button" className="code-tree-retry" onClick={st.retry}>
                      <RefreshCw size={11} />重试
                    </button>
                  </div>
                )
              }
              const data = st.data
              if (!data) return null
              const rootNode: KnowledgeCodeFileNode = data.kind === 'dir'
                ? { path: p, kind: 'dir', children: data.tree ?? [] }
                : {
                    path: p,
                    kind: 'file',
                    content: data.content,
                    binary: typeof data.content !== 'string' ? true : undefined,
                    size: data.size,
                  }
              return (
                <div key={p}>
                  {/* 目录截断提示(契约 partial:true;按原因区分文案,照旧逐路径块) */}
                  {data.partial && (
                    <div className="code-tree-note">
                      <span className="bdg b-amber bdg-mini">
                        {data.partial_reason === 'size'
                          ? '目录内容过大,仅部分加载'
                          : '目录过大,仅加载前 200 个文件'}
                      </span>
                    </div>
                  )}
                  <CodeTreeNode node={rootNode} depth={0} selPath={selPath} onSelect={setSelPath} />
                </div>
              )
            })}
          </div>
        ))}
      </aside>

      {/* 右栏预览:头部路径 + 来源标注 + 重新拉取(refresh=1);md/代码/二进制分流 */}
      <section className="code-preview">
        <div className="code-preview-head">
          <FileText size={13} className="ic" />
          <span className="mono code-preview-path" title={selPath ?? undefined}>
            {selPath ?? '未选择文件'}
          </span>
          {selSource && (
            <span className="chip">
              <GitBranch size={12} />{repoLabelOf(selSource.repo_id)} · {selSource.branch}
            </span>
          )}
          <div className="code-preview-acts">
            <Button variant="ghost" size="sm" disabled={!selPath} onClick={handleRefresh}>
              <RefreshCw size={13} />重新拉取
            </Button>
          </div>
        </div>
        <div className="code-preview-body">{previewBody}</div>
      </section>
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

  // ---- 权限消费(R3 预埋 permissions;can_publish/can_promote 为 R3.F2 扩展) ----
  // 发布:后端 can_publish 优先(超管全真);缺省时回退现状 —— permissions 已返回用
  // can_edit 代理,permissions 也没有则按本地角色 owner/editor 判断
  const perms = entry?.permissions
  const canPublish = !!entry && entry.status === 'draft'
    && (typeof perms?.can_publish === 'boolean'
      ? perms.can_publish
      : (perms ? !!perms.can_edit : myRole === 'owner' || myRole === 'editor'))
  // 提升:后端 can_promote 优先(修 R2 审计「超管非成员不可见提升按钮」缺口);
  // 缺省时回退现状本地 owner 判断;仅项目级条目可提升(project_id 门控后端同样成立)
  const canPromote = !!entry?.project_id
    && (typeof perms?.can_promote === 'boolean' ? perms.can_promote : myRole === 'owner')
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
  // R28.F2:正文大纲 h1-h3(id 与 renderMarkdown 输出同规则);编辑保存随 content 刷新。
  // 代码引用区不在大纲内(只收正文标题);须在早退分支前取值(hooks 顺序)
  const outline = useMemo(
    () => (entry?.content ? extractOutline(entry.content) : []),
    [entry?.content],
  )
  const repoLabelOf = (repoId: string) => {
    const r = project?.repos?.find((x) => x.repo_id === repoId)
    return repoDisplayName(repoId, r?.gitlab_repo_url)
  }

  // ---- BUG-KB-005:目录点击项持久 active 高亮 + 滚动期间屏蔽目录 hover ----
  // sticky 目录在平滑滚动期间整体上移、经过静止指针,滚动结束 Chromium 按指针最后坐标
  // 重算 :hover → 高亮落在非点击项。双管齐下:点击项记入 activeTocId(持久高亮,样式
  // 区分于 hover);滚动期间给 .md-toc 加 .locking(pointer-events:none),scrollend
  // 后解除(800ms 兜底,覆盖不支持 scrollend 的内核/未发生滚动的点击)。gen 计数使
  // 连点时仅最后一次滚动负责解锁。
  const [activeTocId, setActiveTocId] = useState<string | null>(null)
  const [tocLocked, setTocLocked] = useState(false)
  const tocLockTimer = useRef<number | null>(null)
  const tocLockGen = useRef(0)
  useEffect(() => () => {
    if (tocLockTimer.current !== null) window.clearTimeout(tocLockTimer.current)
  }, [])
  const handleTocClick = (id: string) => {
    setActiveTocId(id)
    setTocLocked(true)
    const gen = ++tocLockGen.current
    const unlock = () => {
      if (gen !== tocLockGen.current) return // 已被后续点击接管
      tocLockGen.current += 1
      document.removeEventListener('scrollend', unlock, true)
      if (tocLockTimer.current !== null) {
        window.clearTimeout(tocLockTimer.current)
        tocLockTimer.current = null
      }
      setTocLocked(false)
    }
    // scrollend 不冒泡,滚动容器是 .route-scroll → 用捕获监听在 document 上收到
    document.addEventListener('scrollend', unlock, { once: true, capture: true })
    if (tocLockTimer.current !== null) window.clearTimeout(tocLockTimer.current)
    tocLockTimer.current = window.setTimeout(unlock, 800)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  // ---- R3:编辑 / 删除(editable_fields 字段白名单由后端算好,前端零猜测直接消费) ----
  const editFields = perms?.editable_fields
  const fieldEditable = (f: string) => !editFields || editFields.includes(f)
  // AI 条目白名单只含 tags → 编辑态其余字段全禁用 + 提示条(逐字照分片「文案清单」)
  const tagsOnly = !!editFields && editFields.length > 0 && !editFields.includes('title')

  const updateMut = useUpdateKnowledge(entryId)
  const deleteMut = useDeleteKnowledge(entryId)

  const [editOpen, setEditOpen] = useState(false)
  const [editType, setEditType] = useState<KnowledgeType>('code_snippet')
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [editTags, setEditTags] = useState('')
  const [contentPreview, setContentPreview] = useState(false)
  const [editRepoId, setEditRepoId] = useState('')
  const [editBranch, setEditBranch] = useState('')
  const [editPaths, setEditPaths] = useState<string[]>([''])
  const [editErr, setEditErr] = useState<string | null>(null)
  const [showDelete, setShowDelete] = useState(false)

  // 编辑表单仓库下拉(项目绑定仓库;平台级条目无项目上下文 → 仅保留原值可显示)
  const repoOptions = useMemo(() => {
    const opts = (project?.repos ?? []).map((r) => ({
      value: r.repo_id,
      label: `${repoShortName(r.gitlab_repo_url)}（${repoRoleLabel[r.role] ?? '其他'}）`,
    }))
    if (editRepoId && !opts.some((o) => o.value === editRepoId)) {
      opts.unshift({ value: editRepoId, label: repoDisplayName(editRepoId) })
    }
    return opts
  }, [project, editRepoId])

  // 分支下拉:选仓库后加载;default 分支置顶并标注(照 R1)
  const branchesQ = useProjectRepoBranches(entry?.project_id ?? '', editRepoId)
  const branchOptions = useMemo(() => {
    const list = [...(branchesQ.data ?? [])].sort((a, b) => Number(b.default) - Number(a.default))
    const opts = list.map((b) => ({ value: b.name, label: b.default ? `${b.name}（默认）` : b.name }))
    // 分支未随项目分支列表返回(平台级条目/分支已删):保留原值可显示
    if (editBranch && !opts.some((o) => o.value === editBranch)) {
      opts.unshift({ value: editBranch, label: editBranch })
    }
    return opts
  }, [branchesQ.data, editBranch])
  // 分支加载完成:当前值失效(或为空)时自动选中 default 分支,避免空值提交(照 R1)
  useEffect(() => {
    const list = branchesQ.data
    if (!list || list.length === 0) return
    setEditBranch((cur) => (
      cur && list.some((b) => b.name === cur) ? cur : (list.find((b) => b.default) ?? list[0]).name
    ))
  }, [branchesQ.data])

  // 非空路径数(提交时剔除空行;上限 10,照 R1)
  const validEditPaths = useMemo(
    () => editPaths.map((p) => p.trim()).filter(Boolean),
    [editPaths],
  )
  // 条目是否含代码引用(A 型)——编辑按原条目形态渲染对应表单,不做 A↔B 互转
  const isCodeEntry = codeSources.length > 0

  // 打开编辑:照 R1 双类型表单结构回填(A 型回填代码引用,B 型回填正文)
  const openEdit = () => {
    if (!entry) return
    setEditType(entry.type)
    setEditTitle(entry.title)
    setEditContent(entry.content ?? '')
    setEditTags((entry.tags ?? []).join(','))
    setContentPreview(false)
    const src = (entry.source_links ?? []).find(isCodeSource)
    setEditRepoId(src?.repo_id ?? '')
    setEditBranch(src?.branch ?? '')
    setEditPaths(src?.paths?.length ? [...src.paths] : [''])
    setEditErr(null)
    setEditOpen(true)
  }

  // 保存:仅提交 editable_fields 放行的字段(AI 条目只带 tags,避开 400 20013)
  const handleSave = () => {
    if (!entry || updateMut.isPending) return
    if (fieldEditable('title') && !editTitle.trim()) {
      setEditErr('请输入标题')
      return
    }
    if (isCodeEntry && fieldEditable('source_links')) {
      if (!editRepoId) {
        setEditErr('请先选择仓库')
        return
      }
      if (validEditPaths.length === 0) {
        setEditErr('请至少填写一个路径')
        return
      }
    }
    const payload: UpdateKnowledgePayload = {}
    if (fieldEditable('title')) payload.title = editTitle.trim()
    if (fieldEditable('type')) payload.type = editType
    if (fieldEditable('tags')) payload.tags = editTags.split(',').map((t) => t.trim()).filter(Boolean)
    if (fieldEditable('content')) payload.content = editContent
    if (isCodeEntry && fieldEditable('source_links')) {
      payload.source_links = [{
        type: 'code', repo_id: editRepoId, branch: editBranch, paths: validEditPaths,
      }]
    }
    updateMut.mutate(payload, {
      onSuccess: () => {
        setEditOpen(false)
        showToast('ok', '已保存') // 详情经 invalidate 自动刷新(徽章/正文/代码引用区同步)
      },
      onError: (e) => setEditErr(e instanceof Error ? e.message : '保存失败'),
    })
  }

  // 删除:成功关窗回列表 + toast(列表缓存已随 hook invalidate)
  const handleDelete = () => {
    if (!entry || deleteMut.isPending) return
    deleteMut.mutate(undefined, {
      onSuccess: () => {
        setShowDelete(false)
        showToast('ok', '已删除')
        const pid = entry.project_id || projectId
        nav(pid ? `/projects/${pid}/knowledge` : '/knowledge')
      },
      onError: (e) => showToast('err', e instanceof Error ? e.message : '删除失败'),
    })
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
  // R28.F2:大纲 ≥2 条启用左右模式(左目录 + 右正文),否则退单栏现状;
  // A 型说明文字全宽放工作台上方,不渲染大纲(大纲仅 B 型保留)
  const showToc = outline.length >= 2 && codeSources.length === 0
  const tags = entry.tags ?? []

  return (
    <div className="page wide">
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
            <Button variant="outline" size="sm" onClick={openEdit}>
              编辑
            </Button>
          )}
          {canDelete && (
            <Button variant="danger" size="sm" onClick={() => setShowDelete(true)}>
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

      {/* 正文区(B 型左右模式):大纲 ≥2 条 → 左 .md-toc 目录 + 右正文;
          A 型不渲染大纲 → 单栏,说明卡全宽在工作台上方。目录项点击平滑滚动到对应标题 id */}
      <div className={showToc ? 'md-layout' : undefined}>
        {showToc && (
          <aside className={`md-toc${tocLocked ? ' locking' : ''}`}>
            <div className="md-toc-title">目录</div>
            {outline.map((o) => (
              <a
                key={o.id}
                href={`#${o.id}`}
                className={`md-toc-item lv${o.level}${activeTocId === o.id ? ' active' : ''}`}
                title={o.text}
                onClick={(e) => {
                  e.preventDefault()
                  handleTocClick(o.id)
                }}
              >
                {o.text}
              </a>
            ))}
          </aside>
        )}
        <div className={showToc ? 'md-main' : isCodeEntry ? 'entry-code-zone' : undefined}>
          {/* 正文卡:.md 渲染 content(B 型正文 / A 型说明文字,普通文档流随页滚走) */}
          {showBodyCard && (
            <Card className="p-5 mb-5">
              {hasContent ? (
                <div className="md" dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.content) }} />
              ) : (
                <div className="empty">暂无内容</div>
              )}
            </Card>
          )}

          {/* 代码引用区(仅 A 型):「关联代码」工作台 —— 左文件树 + 右文件预览;
              说明文字(content)已在上方正文卡全宽渲染,A 型不出大纲;
              .entry-code-dock 粘性钉屏(页面滚动时标题+树+预览钉在视口内,树/预览各自内滚;
              sticky top 相对 .route-scroll 滚动口,topbar 在滚动口外,8px = 视口 58px);
              .entry-code-zone::after 垫高给粘性留行程(末元素无滚动余量 sticky 不生效) */}
          {codeSources.length > 0 && (
            <div className="entry-code-dock flex flex-col gap-3">
              <div className="card-title shrink-0">
                <FileCode size={15} />关联代码
              </div>
              <CodeWorkbench
                entryId={entry.entry_id}
                sources={codeSources}
                repoLabelOf={repoLabelOf}
              />
            </div>
          )}
        </div>
      </div>

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

      {/* 编辑 Dialog(R3:照 R1 双类型表单结构回填;AI 条目按 editable_fields 仅放行 tags) */}
      <Dialog open={editOpen} onOpenChange={(o) => { if (!o) setEditOpen(false) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑条目</DialogTitle>
            <DialogDescription>修改知识条目的内容</DialogDescription>
          </DialogHeader>
          {/* AI 归档条目限制提示(逐字照分片「文案清单」) */}
          {tagsOnly && (
            <div className="flex items-center gap-2 p-3 rounded-md bg-amber-bg border border-amber-border">
              <AlertCircle className="w-4 h-4 text-amber-fg flex-shrink-0" />
              <p className="text-sm text-amber-fg">AI 归档条目仅支持编辑标签</p>
            </div>
          )}
          <div className="flex flex-col gap-3 py-3">
            {isCodeEntry ? (
              <>
                {/* A 型:标题/类型/标签/说明 + 仓库/分支/路径(R1「关联代码」表单回填) */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">标题</label>
                  <Input
                    placeholder="请输入标题"
                    value={editTitle}
                    disabled={!fieldEditable('title')}
                    onChange={(e) => setEditTitle(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">类型</label>
                  <Select
                    options={newEntryTypeOptions}
                    value={editType}
                    disabled={!fieldEditable('type')}
                    onChange={(e) => setEditType(e.target.value as KnowledgeType)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">标签</label>
                  <Input
                    placeholder="多个标签用英文逗号分隔"
                    value={editTags}
                    disabled={!fieldEditable('tags')}
                    onChange={(e) => setEditTags(e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">说明</label>
                  <Textarea
                    placeholder="为什么这段代码值得沉淀?(Markdown,可选)"
                    value={editContent}
                    disabled={!fieldEditable('content')}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={3}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">仓库</label>
                  <Select
                    options={repoOptions}
                    value={editRepoId}
                    placeholder="请选择仓库"
                    disabled={!fieldEditable('source_links') || !entry.project_id}
                    onChange={(e) => { setEditRepoId(e.target.value); setEditBranch('') }}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">分支</label>
                  <Select
                    options={branchOptions}
                    value={editBranch}
                    placeholder={!editRepoId
                      ? '请先选择仓库'
                      : (branchesQ.isLoading ? '分支加载中...' : undefined)}
                    disabled={!fieldEditable('source_links') || !entry.project_id
                      || !editRepoId || branchesQ.isLoading}
                    onChange={(e) => setEditBranch(e.target.value)}
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
                    {editPaths.map((p, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <Input
                          className="flex-1 font-mono text-[12.5px]"
                          placeholder="如 backend/app/services/"
                          value={p}
                          disabled={!fieldEditable('source_links')}
                          onChange={(e) => setEditPaths((arr) => arr.map((x, j) => (j === i ? e.target.value : x)))}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={editPaths.length <= 1 || !fieldEditable('source_links')}
                          title="删除此路径"
                          onClick={() => setEditPaths((arr) => arr.filter((_, j) => j !== i))}
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
                      disabled={editPaths.length >= PATHS_LIMIT || !fieldEditable('source_links')}
                      title={editPaths.length >= PATHS_LIMIT ? '路径最多 10 个' : undefined}
                      onClick={() => setEditPaths((arr) => [...arr, ''])}
                    >
                      <Plus size={13} />添加路径
                    </Button>
                  </div>
                </div>
              </>
            ) : (
              <>
                {/* B 型:类型/标题/内容(编辑|预览)/标签(R1「直接创建」表单回填) */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">类型</label>
                  <Select
                    options={newEntryTypeOptions}
                    value={editType}
                    disabled={!fieldEditable('type')}
                    onChange={(e) => setEditType(e.target.value as KnowledgeType)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">标题</label>
                  <Input
                    placeholder="请输入标题"
                    value={editTitle}
                    disabled={!fieldEditable('title')}
                    onChange={(e) => setEditTitle(e.target.value)}
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
                      {editContent.trim() ? (
                        <div dangerouslySetInnerHTML={{ __html: renderMarkdown(editContent) }} />
                      ) : (
                        <span className="text-text-muted">暂无内容</span>
                      )}
                    </div>
                  ) : (
                    <Textarea
                      placeholder="请输入内容"
                      value={editContent}
                      disabled={!fieldEditable('content')}
                      onChange={(e) => setEditContent(e.target.value)}
                      rows={5}
                    />
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-text">标签</label>
                  <Input
                    placeholder="多个标签用英文逗号分隔"
                    value={editTags}
                    disabled={!fieldEditable('tags')}
                    onChange={(e) => setEditTags(e.target.value)}
                  />
                </div>
              </>
            )}
            {/* 保存失败提示(服务端错误码 message 透传,含 400 20013「AI 条目仅支持编辑标签」) */}
            {editErr && (
              <div className="flex items-start gap-2 p-3 rounded-md bg-red-bg border border-red-border">
                <AlertCircle className="w-4 h-4 text-red-fg mt-0.5 flex-shrink-0" />
                <p className="text-sm text-red-fg">{editErr}</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={updateMut.isPending
                || (fieldEditable('title') && !editTitle.trim())
                || (isCodeEntry && fieldEditable('source_links')
                  && (!editRepoId || validEditPaths.length === 0))}
            >
              {updateMut.isPending ? '保存中...' : '保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 Dialog(R3:危险按钮;确认文案逐字照分片「文案清单」) */}
      <Dialog open={showDelete} onOpenChange={(o) => { if (!o) setShowDelete(false) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除</DialogTitle>
            <DialogDescription>删除后不可恢复,确认删除该条目?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowDelete(false)}>取消</Button>
            <Button variant="danger" onClick={handleDelete} disabled={deleteMut.isPending}>
              {deleteMut.isPending ? '删除中...' : '删除'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {ToastEl}
    </div>
  )
}
