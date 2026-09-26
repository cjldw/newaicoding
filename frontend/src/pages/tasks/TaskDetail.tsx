/**
 * TaskDetail — 任务工作台(R4;照抄重写 vp #/t/T-301,R4.F4 / BUG-UI-066 二修)
 *
 * 版式 = vp pageTask 骨架逐元素照抄(docs/…/vp/index.html L1458-1483):
 *   .page.wide(全出血纵向 flex)
 *   └ .wb-head(返回 ghost icon-btn + .ttl 类型徽章/{短id} · {标题}/状态徽章 + .acts;次行 .chip-row)
 *     ※ BUG-UI-080(用户口径):原 head 下方的流程 stepper 带(FLOW_STEPS 7 步)已整段移除,头带直接衔接 .wb
 *   └ .wb(grid;有树 236px | minmax(0,1fr) | 384px,无树 .n2 → minmax(0,1fr) | 384px;1px 分隔线,无 gap 无 padding)
 *      ├ col-tree  文件树(仅 dev 且非 pending;非 dev 任务不渲染 → wb 加 .n2 两栏,中栏占 1fr 不再压窄)
 *      ├ col-center.wb-mid  中栏 centerPane:按 type/status 五分支(requirement/dev/dev pending/test/release)
 *      └ col-right  右栏 rightPane:恒为 对话/终端/活动 三 Tab
 * 所有 twrap 三连(圆角/边框/阴影归零)已收敛为 .twrap-fill 类;其余静态内联样式见 globals.css「wb 内联样式收敛」区段,
 * 仅拖拽实时宽度 / 树层级缩进等动态值保留内联。
 *
 * 能力保留(R4.F1/F2,零回归):面板全屏(fixed 覆盖层不重挂载)、显式保存+自动保存、
 * 终端/对话导出、终端多 tab、@ 补全、发送 pending、错误 toast、左右栏拖拽 sash(叠加在
 * col-tree 右缘 / col-right 左缘,不进入 grid 流,保持 vp 三节 点 DOM)。
 *
 * 面包屑(BUG-UI-063 链):项目 / {项目名} / {需求短id} / 任务 {短id},BreadcrumbOverrideProvider。
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Square, Sparkles, FileCode, FlaskConical, Rocket, GitBranch, Box, Server,
  GitCommit, Eye, FolderOpen, FileText, MessageSquare, Terminal, Activity, Maximize2, Minimize2,
  Save, Clock, Check, ExternalLink, Loader2,
} from 'lucide-react'
import CodeEditor from '@/components/Editor'
import DiffViewer from '@/components/DiffViewer'
import FileTree from '@/components/FileTree'
import { PreviewPanel } from '@/components/PreviewPanel'
import { TerminalPanel } from '@/components/TerminalPanel'
import { TaskChat } from '@/components/TaskChat'
import { ActivityStream } from '@/components/ActivityStream'
import TestCasesReview from '@/pages/tasks/TestCasesReview'
import TestReport from '@/pages/tasks/TestReport'
import DeployStatus from '@/pages/tasks/DeployStatus'
import { BreadcrumbOverrideProvider, type CrumbItem } from '@/components/layout/Breadcrumb'
import { useToast } from '@/hooks/useToast'
import {
  useTaskDetail, useStopTask, useTaskPreviews,
} from '@/api/tasks'
import {
  useTaskFiles, useTaskFileContent, useUpdateTaskFileContent,
  useTaskDiff, useTaskChanges,
} from '@/api/files'
import { useProjectDetail } from '@/api/projects'
import { useRequirementDetail } from '@/api/requirements'
import { useOfflineTask } from '@/api/deploy'
import { createTerminalSession } from '@/api/terminal'
import { useDragSash } from '@/hooks/useDragSash'
import { renderMarkdown } from '@/utils/markdown'

/* ------------------------------------------------------------------ */
/* vp 徽章/类型映射(vp L754-766,原值照抄;timeout 为 React 任务态补充) */
/* ------------------------------------------------------------------ */
const VP_ST: Record<string, { label: string; bdg: string }> = {
  draft: { label: '草稿', bdg: 'b-zinc' },
  polishing: { label: '打磨中', bdg: 'b-blue' },
  reviewing: { label: '评审中', bdg: 'b-amber' },
  approved: { label: '已评审', bdg: 'b-green' },
  in_progress: { label: '开发中', bdg: 'b-blue' },
  done: { label: '已完成', bdg: 'b-green' },
  archived: { label: '已归档', bdg: 'b-zinc' },
  rejected: { label: '已驳回', bdg: 'b-red' },
  cancelled: { label: '已取消', bdg: 'b-zinc' },
  pending: { label: '排队中', bdg: 'b-zinc' },
  running: { label: '运行中', bdg: 'b-blue' },
  cases_review: { label: '用例评审', bdg: 'b-amber' },
  passed: { label: '测试通过', bdg: 'b-green' },
  failed: { label: '失败', bdg: 'b-red' },
  deploying: { label: '部署中', bdg: 'b-amber' },
  deployed: { label: '已上线', bdg: 'b-green' },
  // React 后端特有状态(vp 无);沿用失败红色系
  timeout: { label: '已超时', bdg: 'b-red' },
}
const VP_TYPE: Record<string, { cn: string; icon: typeof Sparkles; bdg: string }> = {
  requirement: { cn: '打磨', icon: Sparkles, bdg: 'b-violet' },
  dev: { cn: '开发', icon: FileCode, bdg: 'b-blue' },
  test: { cn: '测试', icon: FlaskConical, bdg: 'b-violet' },
  release: { cn: '发布', icon: Rocket, bdg: 'b-amber' },
}

/** vp stB(L767):状态徽章;running 时带 pulse dot */
function StatusBadge({ status, pulse }: { status: string; pulse: boolean }) {
  const m = VP_ST[status] ?? { label: status, bdg: 'b-zinc' }
  return (
    <span className={`bdg ${m.bdg}`}>
      <span className={`dot${pulse ? ' pulse' : ''}`} />
      {m.label}
    </span>
  )
}
/** vp tpB(L768):类型徽章(图标 + 中文) */
function TypeBadge({ type }: { type: string }) {
  const m = VP_TYPE[type] ?? VP_TYPE.dev
  const Ic = m.icon
  return (
    <span className={`bdg ${m.bdg}`}>
      <Ic size={12} />
      {m.cn}
    </span>
  )
}

/** 短 id 展示(vp 任务号形如 T-301;React 为 UUID → 取前 8 位,与列表页口径一致) */
const shortId = (id: string | null | undefined) => (id ? id.slice(0, 8) : '—')

/** 从 unified diff 文本统计 +/- 行数(vp d-chip 的 +N −M 角标) */
function diffStat(diff: string): { add: number; del: number } {
  let add = 0
  let del = 0
  for (const ln of diff.split('\n')) {
    if (ln.startsWith('+') && !ln.startsWith('+++')) add += 1
    else if (ln.startsWith('-') && !ln.startsWith('---')) del += 1
  }
  return { add, del }
}

/** 中栏 Tab Key:五种 centerPane 分支的并集(vp data-t 命名) */
type CenterTab = 'edit' | 'diff' | 'prev' | 'prd' | 'files' | 'cases' | 'report' | 'log' | 'conf' | 'merge'
type RightTab = 'chat' | 'term' | 'act'

export default function TaskDetail() {
  const { taskId = '' } = useParams<{ taskId: string }>()
  const nav = useNavigate()
  const { data: task } = useTaskDetail(taskId)
  const [, showToast, ToastEl] = useToast()

  // BUG-UI-064:面板全屏状态(null=正常;面板 CSS 提升为 fixed 覆盖层,不重挂载)
  const [fullscreen, setFullscreen] = useState<'chat' | 'term' | 'editor' | null>(null)
  // 编辑器当前草稿(供显式「保存」;自动保存链路保留)
  const [editorDraft, setEditorDraft] = useState<string | null>(null)
  // 右栏 Tab(vp rightPane:对话/终端/活动;初始 chat,tab on ⇔ pane 显示同步)
  const [rightTab, setRightTab] = useState<RightTab>('chat')
  // 中栏 Tab(按任务类型分支,初始取该分支第一个)
  const [centerTab, setCenterTab] = useState<CenterTab>('edit')
  // 编辑器当前文件
  const [selectedPath, setSelectedPath] = useState('')
  const [enabled, setEnabled] = useState(false) // 点选文件后才拉内容
  // 当前查看的 diff 文件
  const [diffPath, setDiffPath] = useState<string | null>(null)

  // R4.F2:左右栏拖拽宽度(vp 初始 236/384);sash 叠加在分栏边缘,不进 grid 流
  const [leftW, onLeftSashDown] = useDragSash(236, { min: 220, max: 480 })
  const [rightW, onRightSashDown] = useDragSash(384, { min: 320, max: 640, invert: true })

  // Esc 退出全屏
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFullscreen(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const toggleFullscreen = (panel: 'chat' | 'term' | 'editor') =>
    setFullscreen((cur) => (cur === panel ? null : panel))

  const { data: previews } = useTaskPreviews(taskId)
  const stopTask = useStopTask(taskId)
  const offlineTask = useOfflineTask(taskId)

  // 文件树 / 变更 / 文件内容 / diff 数据
  const { data: filesData, refetch: refetchFiles } = useTaskFiles(taskId, '/workspace/main')
  const { data: changesData, refetch: refetchChanges } = useTaskChanges(taskId)
  const { data: fileData } = useTaskFileContent(taskId, enabled ? selectedPath : '')
  const saveFile = useUpdateTaskFileContent()
  const { data: diffData } = useTaskDiff(taskId)

  // 归属数据(面包屑 + requirement PRD 面板):后端 R4.F4 起返回 project_id/req_id
  const { data: project } = useProjectDetail(task?.project_id ?? '')
  const { data: req } = useRequirementDetail(task?.req_id ?? '')

  const previewItem: { port: number; preview_url: string; status: string } | null =
    (previews as unknown as { items?: { port: number; preview_url: string; status: string }[] })?.items?.[0] ?? null

  // watcher 无轮询时兜底:每 15s 刷新变更列表(running 时)
  useEffect(() => {
    if (task?.status !== 'running') return
    const timer = setInterval(() => refetchChanges(), 15000)
    return () => clearInterval(timer)
  }, [task?.status, refetchChanges])

  // BUG-UI-065 保留:切到 Diff 且未选文件时,自动选第一个变更文件
  useEffect(() => {
    if (centerTab !== 'diff' || diffPath) return
    const first = changesData?.repos?.[0]?.files?.[0]?.path
    if (first) setDiffPath(first)
  }, [centerTab, diffPath, changesData])

  // 中栏初始 Tab:类型分支确定后落到该分支第一个 Tab(vp centerPane 各分支首个 tab)
  useEffect(() => {
    const first: Record<string, CenterTab> = {
      dev: 'edit', requirement: 'prd', test: 'cases', release: 'log',
    }
    const target = first[task?.type ?? 'dev'] ?? 'edit'
    setCenterTab((cur) => (cur === target ? cur : target))
  }, [task?.type])

  // 变更文件计数(Diff Tab .n 徽章 + 文件树「变更文件」计数)
  const changedCount = useMemo(
    () => (changesData?.repos ?? []).reduce((n, g) => n + (g.files?.length ?? 0), 0),
    [changesData],
  )
  // 变更文件平铺(中栏 d-chips 用);+/- 统计从 useTaskDiff 的 diff 文本计算
  const changedFiles = useMemo(
    () => (changesData?.repos ?? []).flatMap((g) => g.files ?? []),
    [changesData],
  )
  const diffOf = (path: string | null) => (diffData?.files ?? []).find((f) => f.path === path)

  /** unified diff → DiffViewer 入参(old/new 行拆分,沿用 R4.F2 口径) */
  function currentDiff(): { old: string; new: string } | null {
    const hit = diffOf(diffPath)
    if (!hit) return null
    const oldLines: string[] = []
    const newLines: string[] = []
    for (const ln of hit.diff.split('\n')) {
      if (ln.startsWith('-') && !ln.startsWith('---')) oldLines.push(ln.slice(1))
      else if (ln.startsWith('+') && !ln.startsWith('+++')) newLines.push(ln.slice(1))
      else if (!ln.startsWith('@@')) { oldLines.push(ln.replace(/^ /, '')); newLines.push(ln.replace(/^ /, '')) }
    }
    return { old: oldLines.join('\n'), new: newLines.join('\n') }
  }

  const handleSaveDraft = () => {
    if (!selectedPath || editorDraft === null) return
    saveFile.mutate({ taskId, path: selectedPath, content: editorDraft })
  }

  // 面包屑(vp L1482:项目 / {项目名} / {需求} / 任务 {短id};数据未就绪时退回通用链)
  const crumbs: CrumbItem[] = useMemo(() => {
    const list: CrumbItem[] = [{ label: '项目', href: '/projects' }]
    if (project) list.push({ label: project.name, href: `/projects/${project.project_id}` })
    if (req) list.push({ label: shortId(req.req_id), href: `/requirements/${req.req_id}` })
    list.push({ label: `任务 ${shortId(taskId)}` })
    return list
  }, [project, req, taskId])

  if (!task) {
    return (
      <div className="page wide page-fill">
        <div className="page-loading"><Loader2 size={16} className="animate-spin" />加载中...</div>
      </div>
    )
  }

  const isRun = task.status === 'running'
  // vp L1465:文件树仅 dev 且非挂起显示
  const showTree = task.type === 'dev' && task.status !== 'pending'
  // BUG-UI-081(用户口径):requirement(打磨)任务面向产品,对话为主工作区 → 左右对调
  // (对话/终端/活动 移中栏占 1fr,PRD/工作区 移右栏 384px);dev/test/release 面向开发者保持现状
  const swapPanes = task.type === 'requirement'
  const tabCls = (key: CenterTab | RightTab, cur: string) => `tab${cur === key ? ' on' : ''}`

  /* ---------------- wb-head acts(vp L1462-1464 条件) ---------------- */
  // running → 停止任务(btn-danger);test → 创建发布任务(驳回回开发入口在中栏 TestReport 面板,带标题/描述输入);release → 打开:{port} + 下线;其余空
  let acts: ReactNode = null
  if (isRun) {
    acts = (
      <button className="btn btn-danger" onClick={() => stopTask.mutate()}>
        <Square size={13} />停止任务
      </button>
    )
  }
  if (task.type === 'test') {
    acts = (
      <>
        <button
          className="btn btn-pri"
          onClick={() => {
            // vp 演示口径:发布任务在需求页创建
            if (req) nav(`/requirements/${req.req_id}`)
            else showToast('info', '发布任务在需求页创建')
          }}
        >
          <Rocket size={13} />创建发布任务
        </button>
      </>
    )
  }
  if (task.type === 'release') {
    acts = (
      <>
        <a
          className="btn"
          href={previewItem?.preview_url || undefined}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => {
            if (!previewItem?.preview_url) {
              e.preventDefault()
              showToast('info', '部署地址未就绪')
            }
          }}
        >
          <ExternalLink size={13} />打开 :{previewItem?.port ?? '—'}
        </a>
        <button className="btn btn-danger" onClick={() => offlineTask.mutate()}>
          <Square size={13} />下线
        </button>
      </>
    )
  }

  /* ---------------- 中栏 centerPane 五分支(vp L1253-1377) ---------------- */

  // 公共 Tab 条(vp:tabs padding:0 10px;background:var(--surface);样式由 .wb .tabs 承接)
  const tabsBar = (nodes: ReactNode) => (
    <div className="tabs">{nodes}</div>
  )

  // ---- Diff 视图(dev/test 共用;vp diff pane 结构:d-chips + 内容 + card-foot) ----
  const diffView = (
    <>
      <div className="d-chips">
        {changedFiles.length === 0 && <span className="small faint">暂无变更文件</span>}
        {changedFiles.map((f) => {
          const st = diffStat(diffOf(f.path)?.diff ?? '')
          return (
            <button
              key={f.path}
              className={`dchip${diffPath === f.path ? ' on' : ''}`}
              onClick={() => setDiffPath(f.path)}
              title={f.path}
            >
              {f.path.split('/').pop()}
              <span className="s"><span className="add">+{st.add}</span> <span className="del">−{st.del}</span></span>
            </button>
          )
        })}
      </div>
      <div className="ed-scroll diff-body">
        {diffPath && currentDiff() ? (
          <DiffViewer oldValue={currentDiff()!.old} newValue={currentDiff()!.new} oldTitle={diffPath} newTitle={diffPath} />
        ) : (
          <div className="empty">该文件暂无变更(diff 数据未就绪或文件不在变更列表)</div>
        )}
      </div>
      <div className="card-foot"><Check size={13} /> 逐文件可接受 / 拒绝(拒绝 = 回滚该文件)· 任务结束生成最终 Diff</div>
    </>
  )

  // ---- dev 工作区(编辑器/Diff/预览;vp L1254-1295;R4.F1/F2 能力挂载点) ----
  // vp 仅定义 dev 的 running/pending 两态;其余态(done/failed/cancelled)沿用本工作区(vu 无规格,见 ui-check 留痕)
  const devCenter = (
    <div className="twrap card twrap-fill">
      {tabsBar(<>
        <button className={tabCls('edit', centerTab)} onClick={() => setCenterTab('edit')}><FileCode size={14} />编辑器</button>
        <button className={tabCls('diff', centerTab)} onClick={() => setCenterTab('diff')}>
          <GitCommit size={14} />Diff{changedCount > 0 && <span className="n">{changedCount}</span>}
        </button>
        <button className={tabCls('prev', centerTab)} onClick={() => setCenterTab('prev')}>
          <Eye size={14} />预览
          {previewItem && <span className="bdg b-green bdg-mini">{previewItem.port} · HMR</span>}
        </button>
      </>)}
      {/* 编辑器 pane:on 态才渲染(fixed 全屏覆盖层时也保持挂载,不重挂实例) */}
      {centerTab === 'edit' && (
        selectedPath ? (
          <div className={fullscreen === 'editor'
            ? 'fixed inset-0 z-[60] p-2 flex flex-col'
            : 'flex-1 min-h-0 flex flex-col'}
          >
            <div className="flex-1 min-h-0">
              <CodeEditor
                value={fileData?.content ?? ''}
                path={selectedPath}
                onSave={(v) => saveFile.mutate({ taskId, path: selectedPath, content: v })}
                onChange={(v) => setEditorDraft(v)}
              />
            </div>
            {/* card-foot(vp L1270)+ R4.F1/F2 保存/状态/全屏(右侧操作区) */}
            <div className="card-foot mt-auto">
              <Eye size={13} /> AI 修改实时同步(watcher)· 保存即写入容器 ·
              <span className="bdg b-blue bdg-mini">任务模式 · 可编辑</span>
              <span className="foot-acts">
                <span className="small faint">{saveFile.isPending ? '保存中…' : editorDraft === null ? '未修改' : '已保存'}</span>
                <button
                  type="button" title="保存文件(Ctrl+S 亦可)"
                  disabled={!selectedPath || editorDraft === null || saveFile.isPending}
                  onClick={handleSaveDraft}
                  className="btn btn-sm btn-ghost"
                >
                  <Save size={13} />保存
                </button>
                <button
                  type="button" title={fullscreen === 'editor' ? '退出全屏' : '编辑器全屏'}
                  className="btn btn-sm btn-ghost icon-btn"
                  onClick={() => toggleFullscreen('editor')}
                >
                  {fullscreen === 'editor' ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                </button>
              </span>
            </div>
          </div>
        ) : (
          <div className="empty empty-fill">
            在左侧选择文件
          </div>
        )
      )}
      {centerTab === 'diff' && diffView}
      {centerTab === 'prev' && <PreviewPanel previewUrl={previewItem?.preview_url ?? null} />}
    </div>
  )

  // ---- dev pending 排队空态(vp L1296-1298 原文;BUG-UI-074:twrap-fill 归零卡片语言,与兄弟分支一致) ----
  const pendingCenter = (
    <div className="twrap card twrap-fill">
      <div className="card-body empty empty-fill">
        <Clock size={20} />
        <div className="empty-tip">任务排队中 · 等待可用 Runner / 项目并发配额(单项目并发 running ≤ 3)</div>
      </div>
    </div>
  )

  // ---- requirement 打磨(vp L1364-1376:PRD 草稿(容器内) / 工作区) ----
  const reqCenter = (
    <div className="twrap card twrap-fill">
      {tabsBar(<>
        <button className={tabCls('prd', centerTab)} onClick={() => setCenterTab('prd')}><FileText size={14} />PRD 草稿(容器内)</button>
        <button className={tabCls('files', centerTab)} onClick={() => setCenterTab('files')}><FolderOpen size={14} />工作区</button>
      </>)}
      {centerTab === 'prd' && (
        <>
          <div className="ed-scroll">
            <div className="card-body">
              {req ? (
                // PRD 排版统一走 .md 作用域类(globals.css);首 h2 为需求标题,顶距由 .md>h2:first-child 归零
                <div className="md">
                  <h2>{req.title}</h2>
                  {req.background && <><h3>背景</h3><div dangerouslySetInnerHTML={{ __html: renderMarkdown(req.background) }} /></>}
                  {req.description && <><h3>方案(AI 打磨生成)</h3><div dangerouslySetInnerHTML={{ __html: renderMarkdown(req.description) }} /></>}
                  {req.acceptance_criteria && <><h3>验收标准</h3><div dangerouslySetInnerHTML={{ __html: renderMarkdown(req.acceptance_criteria) }} /></>}
                </div>
              ) : (
                <div className="empty">需求文档加载中…</div>
              )}
            </div>
          </div>
          <div className="card-foot">草稿仅存在于任务容器 · 评审通过后才 commit 到 {task.work_branch}(评审人个人 token)</div>
        </>
      )}
      {centerTab === 'files' && (
        <div className="ed-scroll">
          <div className="tree">
            <div className="tnode dir"><FolderOpen size={14} /><span className="nm mono">/workspace/main</span></div>
            {(filesData?.items ?? []).map((f) => (
              <div
                key={f.path}
                className={`tnode click${selectedPath === f.path ? ' sel' : ''}`}
                style={{ paddingLeft: 38 + (f.path.split('/').length - 1) * 14 }} // 层级缩进为动态值,保留内联
                onClick={() => setSelectedPath(f.path)}
              >
                <FileText size={14} />
                <span className="nm mono">{f.path}</span>
              </div>
            ))}
            {(filesData?.items ?? []).length === 0 && <div className="empty">容器暂无文件</div>}
          </div>
        </div>
      )}
    </div>
  )

  // ---- test(vp L1299-1330:用例 / 测试报告 / Diff;内嵌既有子页组件,R4.F4 embedded 化) ----
  const testCenter = (
    <div className="twrap card twrap-fill">
      {tabsBar(<>
        <button className={tabCls('cases', centerTab)} onClick={() => setCenterTab('cases')}><FlaskConical size={14} />用例</button>
        <button className={tabCls('report', centerTab)} onClick={() => setCenterTab('report')}><FileText size={14} />测试报告</button>
        <button className={tabCls('diff', centerTab)} onClick={() => setCenterTab('diff')}>
          <GitCommit size={14} />Diff{changedCount > 0 && <span className="n">{changedCount}</span>}
        </button>
      </>)}
      {centerTab === 'cases' && (
        <div className="ed-scroll"><TestCasesReview taskIdProp={taskId} embedded /></div>
      )}
      {centerTab === 'report' && (
        <div className="ed-scroll"><TestReport taskIdProp={taskId} embedded /></div>
      )}
      {centerTab === 'diff' && diffView}
    </div>
  )

  // ---- release(vp L1331-1362:部署日志 / 配置 / 变更) ----
  const releaseCenter = (
    <div className="twrap card twrap-fill">
      {tabsBar(<>
        <button className={tabCls('log', centerTab)} onClick={() => setCenterTab('log')}><Terminal size={14} />部署日志</button>
        <button className={tabCls('conf', centerTab)} onClick={() => setCenterTab('conf')}><Server size={14} />配置</button>
        <button className={tabCls('merge', centerTab)} onClick={() => setCenterTab('merge')}><GitCommit size={14} />变更<span className="n">merge</span></button>
      </>)}
      {centerTab === 'log' && (
        <div className="pane on fill pane-pad">
          <DeployStatus taskIdProp={taskId} embedded />
        </div>
      )}
      {centerTab === 'conf' && (
        <div className="ed-scroll">
          <div className="card-body vstack-12">
            <div className="kvs plain">
              <div className="kv"><label>对外地址</label><div className="mono">{previewItem?.preview_url ?? '—'}</div></div>
              <div className="kv"><label>端口</label><div className="mono">{previewItem?.port ?? '—'}(全平台唯一)</div></div>
              <div className="kv"><label>容器</label><div className="mono">{task.container_id ? `${task.container_id.slice(0, 7)} · 保持运行(不销毁)` : '—'}</div></div>
            </div>
            <div className="small muted">
              对外域名默认 <span className="chip">{'{slug}.{deploy_base_domain}'}</span>(平台设置,超管可配),创建发布任务时可自定义覆盖;部署产物(CHANGELOG.md + deploy-log.txt)由平台 bot token commit 到 master。
            </div>
          </div>
        </div>
      )}
      {centerTab === 'merge' && (
        <div className="card-body vstack-10">
          <div className="kvs plain">
            <div className="kv"><label>Merge</label><div className="mono">{task.work_branch} → master{task.last_commit_sha ? ` · ${task.last_commit_sha.slice(0, 7)}` : ''}</div></div>
            <div className="kv"><label>执行者</label><div>平台 bot token(系统动作,不依赖用户在线)</div></div>
          </div>
          {/* 逐文件变更明细(changes 接口含 additions/deletions):文件 | +/- */}
          {changedFiles.length > 0 && (
            <table className="tbl">
              <thead>
                <tr><th>文件</th><th className="ops">+ / −</th></tr>
              </thead>
              <tbody>
                {changedFiles.map((f) => (
                  <tr key={f.path}>
                    <td>
                      <span className="cell-txt path" title={f.path}>{f.path}</span>
                    </td>
                    <td className="ops num">
                      <span className="add">+{f.additions}</span> <span className="del">−{f.deletions}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )

  // 中栏分支选择(vp centerPane 同序:dev running → dev pending → test → release → requirement 兜底)
  const center = (() => {
    if (task.type === 'dev') return task.status === 'pending' ? pendingCenter : devCenter
    if (task.type === 'test') return testCenter
    if (task.type === 'release') return releaseCenter
    return reqCenter
  })()

  // 对话/终端/活动 面板(vp rightPane 恒三 Tab;BUG-UI-081 起按 swapPanes 决定落中栏还是右栏)
  const rightPane = (
    <div className="twrap card twrap-fill">
      {tabsBar(<>
        <button className={tabCls('chat', rightTab)} onClick={() => setRightTab('chat')}>
          <MessageSquare size={14} />对话
        </button>
        <button className={tabCls('term', rightTab)} onClick={() => setRightTab('term')}>
          <Terminal size={14} />终端
          {/* vp L1438:running 时终端 Tab 带 pulse dot(照抄) */}
          {isRun && <span className="dot pulse dot-ok" />}
        </button>
        <button className={tabCls('act', rightTab)} onClick={() => setRightTab('act')}>
          <Activity size={14} />活动
        </button>
      </>)}
      {/* pane:hidden 保活(终端缓冲/聊天态不丢,R4.F1/F2);显示态 flex 铺满 */}
      <div hidden={rightTab !== 'chat'} className="rpane">
        <TaskChat
          taskId={taskId}
          projectId={task.project_id ?? undefined}
          fullscreen={fullscreen === 'chat'}
          onToggleFullscreen={() => toggleFullscreen('chat')}
        />
      </div>
      {/* BUG-UI-074:三 pane 统一 12px 空气垫(由 .rpane 承接);终端深色视口与 chat/activity 内卡对齐 */}
      <div hidden={rightTab !== 'term'} className="rpane">
        <TerminalPanel
          createSession={() => createTerminalSession(taskId)}
          fullscreen={fullscreen === 'term'}
          onToggleFullscreen={() => toggleFullscreen('term')}
        />
      </div>
      <div hidden={rightTab !== 'act'} className="rpane scroll-y">
        <ActivityStream taskId={taskId} />
      </div>
    </div>
  )

  return (
    <BreadcrumbOverrideProvider crumbs={crumbs}>
      {/* vp L1477:.page.wide 全出血纵向 flex;flex 铺满/零底距由 .page-fill 承接 */}
      <div className="page wide page-fill">
        {/* vp L1466-1476:wb-head(BUG-UI-074 拆两行:主行标题/徽章/acts 右置,次行 chip-row;换行悬挂消除) */}
        <div className="wb-head">
          <div className="wb-head-main">
            <button className="btn btn-ghost icon-btn" title="返回需求" onClick={() => nav(-1)}>
              <ArrowLeft size={15} />
            </button>
            <span className="ttl">
              <TypeBadge type={task.type} />
              <span className="truncate">{shortId(task.task_id)} · {task.title}</span>
              <StatusBadge status={task.status} pulse={isRun} />
              {/* React 补充:失败信息内联提示(vp 无此元素,保留功能性) */}
              {task.error_message && (
                <span className="small err-txt">{task.error_message}</span>
              )}
            </span>
            {/* acts 恒右置(停止/创建发布/打开+下线;BUG-UI-081 复核点) */}
            <span className="acts">{acts}</span>
          </div>
          <div className="wb-head-sub chip-row">
            <span className="chip"><GitBranch size={12} />{task.work_branch}</span>
            <span className="chip"><Box size={12} />{task.container_id ? task.container_id.slice(0, 7) : '—'}</span>
            <span className="chip"><Server size={12} />{task.runner_id ? task.runner_id.slice(0, 8) : '—'}</span>
            {task.last_commit_sha && (
              <span className="chip"><GitCommit size={12} />{task.last_commit_sha.slice(0, 7)}</span>
            )}
          </div>
        </div>

        {/* vp L1478-1481:.wb 栏 grid(无 gap 无 padding;1px 分隔线由 col-* border 提供)
            有树:三栏,拖拽宽度注入模板;无树(非 dev / dev pending):加 n2 类 → minmax(0,1fr)|384px 两栏,
            col-center 无显式列指定,auto-flow 自然落第一列,不再压进 236px 窄列;
            BUG-UI-081:requirement 任务 swapPanes → 对话面板落中栏 1fr(产品主工作区),PRD/工作区落右栏 384px */}
        <div
          className={`wb${showTree ? '' : ' n2'}`}
          style={showTree ? { gridTemplateColumns: `${leftW}px minmax(0,1fr) ${rightW}px` } : undefined}
        >
          {showTree && (
            <section className="col-tree">
              <div className="tree-scroll">
                <FileTree
                  mode="task"
                  files={filesData?.items ?? []}
                  changes={changesData?.repos ?? []}
                  selectedPath={selectedPath}
                  onSelectFile={(p) => { setSelectedPath(p); setEnabled(true); setCenterTab('edit') }}
                  onSelectDiff={(p) => { setDiffPath(p); setCenterTab('diff') }}
                  onRefresh={() => { refetchFiles(); refetchChanges() }}
                />
              </div>
              {/* tree-foot(vp L1238-1243;字段映射真实任务) */}
              <div className="tree-foot">
                <span><b>容器</b> {task.container_id ? `${task.container_id.slice(0, 7)} · devbox:v1` : '—'}</span>
                <span><b>Runner</b> {task.runner_id ? task.runner_id.slice(0, 8) : '—'}</span>
                <span><b>分支</b> {task.work_branch}(基础 = {task.base_branch})</span>
                <span><b>变更</b> 相对 {task.base_branch} 基线全部差异(已 commit + 未 commit)</span>
              </div>
              {/* 左 sash(R4.F2 拖拽;叠加右缘,不进 grid 流) */}
              <div className="sash sash-l" onMouseDown={onLeftSashDown} />
            </section>
          )}

          {/* BUG-UI-081:requirement 任务左右对调 —— 对话面板在中栏(主工作区),PRD/工作区在右栏;
              其余类型保持 中=工作区 / 右=对话终端活动 */}
          {/* 中栏:col-center.wb-mid(vp section 语义) */}
          <section className="col-center wb-mid">{swapPanes ? rightPane : center}</section>

          {/* 右栏:col-right(vp L1433-1456 rightPane) */}
          <section className="col-right">
            {swapPanes ? center : rightPane}
            {/* 右 sash(R4.F2 拖拽;仅在有树的 3 栏布局下生效 —— 无树时右栏占 1fr,拖拽无意义) */}
            {showTree && (
              <div className="sash sash-r" onMouseDown={onRightSashDown} />
            )}
          </section>
        </div>
      </div>
      {ToastEl}
    </BreadcrumbOverrideProvider>
  )
}
