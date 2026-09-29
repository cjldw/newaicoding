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

import { useEffect, useMemo, useState, useCallback, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
// R39:git 操作 Dialog + 身份/权限来源
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/Dialog'
import { useAuthStore } from '@/stores/authStore'
import { ApiError } from '@/api/client'
import { useProjectMembers } from '@/api/projects'
import { useTaskGitCommit, useTaskGitPush } from '@/api/files'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Square, Sparkles, FileCode, FlaskConical, Rocket, GitBranch, Box, Server,
  GitCommit, Eye, FolderOpen, FileText, MessageSquare, Terminal, Activity, Maximize2, Minimize2,
  Save, Clock, Check, ExternalLink, Loader2, RotateCcw, CheckCircle2, Upload,
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
  useTaskDetail, useStopTask, useRetryTask, useTaskPreviews, useFinishTask,
} from '@/api/tasks'
import {
  useTaskFiles, useTaskFileContent, useUpdateTaskFileContent,
  useTaskDiff, useTaskChanges, filesApi,
} from '@/api/files'
import { useQueryClient } from '@tanstack/react-query'
import { useProjectDetail } from '@/api/projects'
import { useRequirementDetail, useRequirementPrdContent } from '@/api/requirements'
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
  // BUG-063:容器启动中(amber 黄,与 running 蓝区分;pulse 动画同 running)
  starting: { label: '启动中', bdg: 'b-amber' },
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
  // 20260929_任务打磨面板全屏:扩展 'prd'(PRD 草稿) / 'files'(工作区) 两中栏
  const [fullscreen, setFullscreen] = useState<'chat' | 'term' | 'editor' | 'prd' | 'files' | null>(null)
  // 20260929_任务停止页面置灰:点停止后置 true → 全页遮罩拦截操作,
  // 容器真正停下(display_status 离开 running/starting)或 mutation 报错时复位
  const [stopRequested, setStopRequested] = useState(false)
  // 20260929_容器重试页面置灰:点重试后置 true → 全页遮罩(与停止同款交互),
  // 容器启动成功(display_status=running)或重试失败/终态落回 failed/cancelled/timeout 时复位
  const [retryRequested, setRetryRequested] = useState(false)
  // 20260929_打磨完成按钮:点「打磨完成」后置 true → 全页遮罩(与停止/重试同款交互),
  // 任务转 done/failed/cancelled/timeout 时复位;提交失败也撤
  const [finishRequested, setFinishRequested] = useState(false)
  // 20260929_任务容器未启动置灰引导:容器门卫状态
  // containerGateOpen=弹框是否显示;containerGateStarting=是否正在启动中(遮罩)
  // display_status ∉ {running, starting} → 门卫生效 → 全页遮罩 + 弹框引导启动
  // sessionStorage 按 taskId 记跳过标记,本会话不重弹(刷新/重进再弹)
  const [containerGateOpen, setContainerGateOpen] = useState(false)
  const [containerGateStarting, setContainerGateStarting] = useState(false)
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
  // R38:Diff 口径切换('all'=基线分支 vs 工作区,默认现状;'head'=HEAD vs 工作区,仅未提交)
  // 切口径 → useTaskDiff/useTaskChanges 的 queryKey 带 scope → 自动换 key refetch
  const [diffScope, setDiffScope] = useState<'all' | 'head'>('all')

  // R39:git 操作(commit/push)状态 + mutations
  const [commitDialogOpen, setCommitDialogOpen] = useState(false)
  const [commitMessage, setCommitMessage] = useState('')
  const gitCommit = useTaskGitCommit()
  const gitPush = useTaskGitPush()
  // R39:权限判定(editor+ 才显示操作行)+ 身份显示
  const { data: membersData } = useProjectMembers(task?.project_id ?? '')
  const me = useAuthStore((s) => s.user)
  // 当前用户在项目中的角色(owner/editor 可操作;viewer 隐藏)
  const myRole = useMemo(() => {
    if (!me || !membersData?.items) return null
    return membersData.items.find((m) => m.user_id === me.user_id)?.role ?? null
  }, [me, membersData])
  // R39:身份展示(name/email 从 commit 响应取 v1;静态占位用当前用户信息)
  const identityName = me?.nickname || me?.gitlab_username || me?.phone || '—'
  const identityEmail = me?.gitlab_username ? `${me.gitlab_username}@zhanqi.com` : (me?.phone ? `${me.phone}@zhanqi.com` : '—')
  // R39:默认 commit message 文案「AI 任务变更 {短id} {YYYY-MM-DD HH:mm}」
  const defaultCommitMessage = useMemo(() => {
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`
    return `AI 任务变更 ${shortId(taskId)} ${ts}`
  }, [taskId])
  // R39:错误码 → toast 文案矩阵(6 条)
  const mapGitError = (err: unknown): string => {
    if (err instanceof ApiError) {
      switch (err.code) {
        case 9001: return '任务无运行中的容器'
        case 2015: return '无变更可提交'
        case 1012: return 'GitLab token 无效,请到个人设置重绑'
        case 1013: return 'token 权限不足(push 被拒)'
        case 2014: return `GitLab 操作失败:${err.message.slice(0, 300)}`
        case 403: return '需要编辑者及以上权限'
      }
    }
    return err instanceof Error ? err.message : '操作失败'
  }
  // R39:点「提交」→ 开 Dialog 预填默认文案
  const handleCommitClick = () => {
    setCommitMessage(defaultCommitMessage)
    setCommitDialogOpen(true)
  }
  // R39:Dialog 确认 → POST commit → 成功关 Dialog + toast;失败保留 message
  const handleCommitConfirm = () => {
    gitCommit.mutate({ taskId, message: commitMessage }, {
      onSuccess: () => {
        showToast('ok', '提交成功')
        setCommitDialogOpen(false)
      },
      onError: (err) => {
        showToast('err', mapGitError(err))
        // Dialog 不关,message 保留
      },
    })
  }
  // R39:点「推送」→ 直发 POST → toast
  const handlePushClick = () => {
    gitPush.mutate(taskId, {
      onSuccess: () => showToast('ok', '推送成功'),
      onError: (err) => showToast('err', mapGitError(err)),
    })
  }

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

  const toggleFullscreen = (panel: 'chat' | 'term' | 'editor' | 'prd' | 'files') =>
    setFullscreen((cur) => (cur === panel ? null : panel))

  const { data: previews } = useTaskPreviews(taskId)
  const stopTask = useStopTask(taskId)
  const retryTask = useRetryTask(taskId)
  const finishTask = useFinishTask(taskId)
  const offlineTask = useOfflineTask(taskId)

  // 文件树 / 变更 / 文件内容 / diff 数据
  const { data: filesData, refetch: refetchFiles, isFetching: filesFetching } = useTaskFiles(taskId, '/workspace/main')
  const { data: changesData, refetch: refetchChanges } = useTaskChanges(taskId, diffScope)
  // R4.F6(BUG-070 复开):内容加载三态外露——此前 isLoading/isError 被丢弃,
  // read 失败(如路径语义错误)静默渲染空编辑器,用户无法分辨「空文件」与「加载失败」
  const {
    data: fileData,
    isLoading: fileContentLoading,
    isError: fileContentError,
    refetch: refetchFileContent,
  } = useTaskFileContent(taskId, enabled ? selectedPath : '')

  // R4.F6 完整文件树管理:selectedPath 全链路升级为容器绝对路径(runner read/write/file_op
  // 均为裸 shell 拼路径,绝对路径是唯一安全语义;树内展示用 basename,由 FileTree 内部处理)
  const queryClient = useQueryClient()
  // 文件树外部刷新令牌:bump → FileTree 清空已加载子级缓存,已展开目录自动重拉
  const [treeRefreshNonce, setTreeRefreshNonce] = useState(0)
  // 目录懒加载:按目录绝对路径 fetchQuery(60s 缓存窗口,折叠再展开不重拉;
  // 刷新链路 refreshFileTree 已 invalidate 全前缀,置旧后 fetchQuery 必真实重拉)
  const loadTaskDir = useCallback(
    (dir: string) =>
      queryClient.fetchQuery({
        queryKey: ['task-files', taskId, dir],
        queryFn: () => filesApi.listTaskFiles(taskId, dir).then((r) => r.data.items),
        staleTime: 60_000,
      }),
    [queryClient, taskId]
  )
  const refreshFileTree = useCallback(() => {
    setTreeRefreshNonce((n) => n + 1)
    refetchFiles()
    refetchChanges()
    // 根层 + 各已展开目录的按目录缓存一并置旧,fetchQuery 下次触发真实重拉
    queryClient.invalidateQueries({ queryKey: ['task-files', taskId] })
  }, [queryClient, taskId, refetchFiles, refetchChanges])
  const saveFile = useUpdateTaskFileContent()
  // R4.F8(BUG-075):diff 数据三态外露——此前失败/空缓存无任何恢复入口,
  // 用户点 chip 只看到误导性「该文件暂无变更」
  const {
    data: diffData,
    isError: diffError,
    isFetching: diffFetching,
    refetch: refetchDiff,
  } = useTaskDiff(taskId, diffScope)

  // 归属数据(面包屑 + requirement PRD 面板):后端 R4.F4 起返回 project_id/req_id
  const { data: project } = useProjectDetail(task?.project_id ?? '')
  const { data: req } = useRequirementDetail(task?.req_id ?? '')

  // R3:PRD 副本读取(免容器预览)— 数据源切换至平台副本接口(降级链服务端内置)
  // 原 prdContainerPath 拼接 + useTaskFileContent 调用已移除(容器离线也可用,核心诉求)
  const {
    data: prdContentData,
    isLoading: prdContentLoading,
    refetch: refetchPrdContent,
  } = useRequirementPrdContent(task?.req_id)

  const previewItem: { port: number; preview_url: string; status: string } | null =
    (previews as unknown as { items?: { port: number; preview_url: string; status: string }[] })?.items?.[0] ?? null

  // watcher 无轮询时兜底:每 15s 刷新变更列表(running 时)
  useEffect(() => {
    if (task?.status !== 'running') return
    const timer = setInterval(() => refetchChanges(), 15000)
    return () => clearInterval(timer)
  }, [task?.status, refetchChanges])

  // R3:PRD 副本读取(免容器预览):15s 轮询刷新平台副本
  // 镜像本文件 refetchChanges 的 15s setInterval 先例——仅 centerTab==='prd' 且任务在跑时 refetch
  useEffect(() => {
    if (task?.status !== 'running') return
    if (centerTab !== 'prd') return
    const timer = setInterval(() => refetchPrdContent(), 15000)
    return () => clearInterval(timer)
  }, [task?.status, centerTab, refetchPrdContent])

  // 20260929_任务停止页面置灰 / 20260929_容器重试页面置灰 / 20260929_打磨完成按钮 / 20260929_任务容器未启动置灰引导:taskId 变化/卸载时遮罩状态复位(防跨任务残留)
  useEffect(() => {
    setStopRequested(false)
    setRetryRequested(false)
    setFinishRequested(false)
    setContainerGateOpen(false)
    setContainerGateStarting(false)
    return () => {
      setStopRequested(false)
      setRetryRequested(false)
      setFinishRequested(false)
      setContainerGateOpen(false)
      setContainerGateStarting(false)
    }
  }, [taskId])

  // 20260929_任务停止页面置灰:轮询监听任务状态(useTaskDetail 已有 5s refetchInterval),
  // display_status 离开 running/starting → 容器已停 → 撤遮罩。
  // 早 return:未请求停止 / task 未就绪 / 仍在跑 → 都不动
  useEffect(() => {
    if (!stopRequested) return
    if (!task) return
    const displaySt = task.display_status ?? task.status
    if (displaySt === 'running' || displaySt === 'starting') return
    setStopRequested(false)
  }, [stopRequested, task])

  // 20260929_容器重试页面置灰:轮询监听任务状态(镜像停止遮罩 effect 写法),
  // display_status=running → 容器启动成功 → 撤遮罩;
  // display_status 落回 failed/cancelled/timeout → 重试失败,放行再次重试 → 也撤;
  // pending/starting 期间保持遮罩(容器启动中)
  useEffect(() => {
    if (!retryRequested) return
    if (!task) return
    const displaySt = task.display_status ?? task.status
    if (displaySt === 'running') {
      setRetryRequested(false)
      return
    }
    if (displaySt === 'failed' || displaySt === 'cancelled' || displaySt === 'timeout') {
      setRetryRequested(false)
    }
  }, [retryRequested, task])

  // 20260929_打磨完成按钮:轮询监听任务状态(镜像重试遮罩 effect 写法),
  // 提交成功 → 任务转 done → 撤遮罩;
  // display_status 落 failed/cancelled/timeout → 提交失败/任务异常 → 也撤放行重试;
  // pending/starting/running 期间保持遮罩(后端处理中)
  useEffect(() => {
    if (!finishRequested) return
    if (!task) return
    const displaySt = task.display_status ?? task.status
    if (displaySt === 'done' || displaySt === 'failed' || displaySt === 'cancelled' || displaySt === 'timeout') {
      setFinishRequested(false)
    }
  }, [finishRequested, task])

  // 20260929_任务容器未启动置灰引导:容器门卫状态机
  // 触发条件:task 数据就绪 + display_status ∉ {running, starting} + 本会话未跳过该 taskId
  // 撤除条件:轮询到 running/starting(容器已起)→ 自动撤遮罩 + 关弹框
  // 与停止遮罩(stopRequested)互斥:停止只在 running,门卫只在非 running,状态天然不相交;
  // 若极端场景交叉(如轮询间隙),以停止遮罩优先(停止遮罩渲染在门卫遮罩之后,z-index 更高)
  useEffect(() => {
    if (!task) return
    const st = task.display_status ?? task.status
    // running/starting → 容器已起或正在起 → 门卫不生效,撤所有门卫态
    if (st === 'running' || st === 'starting') {
      if (containerGateOpen) setContainerGateOpen(false)
      if (containerGateStarting) setContainerGateStarting(false)
      return
    }
    // 非 running/starting → 门卫生效;若用户本会话已点「暂不」(sessionStorage 有 skip 标记)→ 不弹框不遮罩
    const skipKey = `containerGateSkip:${taskId}`
    const skipped = sessionStorage.getItem(skipKey)
    if (skipped) {
      // 已跳过:不弹框;若正在启动中(用户之前点过启动,轮询还没到 running)保持启动中遮罩
      if (containerGateOpen) setContainerGateOpen(false)
      return
    }
    // 未跳过 + 非 running/starting → 弹框 + 遮罩
    if (!containerGateOpen) setContainerGateOpen(true)
  }, [task, taskId, containerGateOpen, containerGateStarting])

  // 20260929_任务容器未启动置灰引导:点「启动」→ 调 retryTask;
  // pending 态后端 retry_task 只收 failed/cancelled/timeout(pending 会报 TASK_REQ_STATUS_INVALID)
  // → 前端 pending 态直接 disabled + toast 提示「排队任务等待调度」,不发起请求
  // 成功:关弹框,遮罩转「容器启动中…」loading 态(轮询到 running 自动撤)
  // 失败:toast 透出后端错误文案,遮罩+弹框保持(用户可再选暂不)
  const handleContainerGateStart = () => {
    const st = task?.display_status ?? task?.status
    if (st === 'pending') {
      showToast('info', '排队任务等待调度')
      return
    }
    setContainerGateStarting(true)
    setContainerGateOpen(false)
    retryTask.mutate(undefined, {
      onSuccess: () => {
        // 成功:遮罩保持(containerGateStarting=true),轮询到 running 自动撤
        // 弹框已关(setContainerGateOpen(false) 在 mutate 前)
      },
      onError: (err: unknown) => {
        // 失败:撤启动中遮罩,重新开弹框,toast 透出后端错误文案
        setContainerGateStarting(false)
        setContainerGateOpen(true)
        const msg = err instanceof Error ? err.message : '启动失败'
        showToast('err', msg)
      },
    })
  }
  // 20260929_任务容器未启动置灰引导:点「暂不」→ 关弹框撤遮罩 + sessionStorage 写 skip 标记
  const handleContainerGateSkip = () => {
    setContainerGateOpen(false)
    sessionStorage.setItem(`containerGateSkip:${taskId}`, '1')
  }

  // BUG-UI-065 保留:切到 Diff 且未选文件时,自动选第一个变更文件
  useEffect(() => {
    if (centerTab !== 'diff' || diffPath) return
    const first = changesData?.repos?.[0]?.files?.[0]?.path
    if (first) setDiffPath(first)
  }, [centerTab, diffPath, changesData])

  // R4.F8(BUG-075):失步自愈——进入 Diff Tab 时变更清单有文件而 diff 数据为空
  // (旧缓存/容器抖动窗口抓取失败),自动补拉一次;不反复重试(失败走可见重试按钮)
  // R38:按 scope 维度独立重试标记(切口径 → queryKey 换 → 数据全新,旧标记不复用)
  const diffAutoRetriedRef = useRef<Record<'all' | 'head', boolean>>({ all: false, head: false })
  useEffect(() => {
    if (centerTab !== 'diff' || diffAutoRetriedRef.current[diffScope]) return
    if (diffFetching) return
    const hasChanges = (changesData?.repos ?? []).some((g) => (g.files ?? []).length > 0)
    const hasDiff = (diffData?.files ?? []).length > 0
    if (hasChanges && !hasDiff) {
      diffAutoRetriedRef.current[diffScope] = true
      refetchDiff()
    }
  }, [centerTab, diffScope, diffData, changesData, diffFetching, refetchDiff])

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

  // 20260929_容器状态动态反馈:1s ticker(驱动时间 chip 每秒刷新)。
  // 依赖 taskId 变化重置;卸载清理 interval。
  // 仅在 starting/running 时渲染时间,其余态不消耗渲染(但 ticker 恒跑保持实现最简;
  // 每秒 setState 成本可忽略,且避免依赖 displaySt 变化时重启 interval 的边界问题)
  // NOTE:必须在 early return 之前,否则违反 React hooks 规则(task 未就绪时 hook 数少)
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [taskId])

  // BUG-063:优先取 display_status(区分「启动中」vs「运行中」);旧后端无字段时回退 status
  const displaySt = task?.display_status ?? task?.status ?? 'pending'
  // starting 也算「在跑」→ pulse dot + 停止按钮
  const isRun = displaySt === 'running' || displaySt === 'starting'

  // 20260929_容器状态动态反馈:elapsed 计算(ms)。
  // 早 return:非 starting/running 或 started_at 缺失 → null(不渲染时间 chip)。
  // <0 或 NaN 兜底 null(旧数据/时钟漂移)
  const elapsedMs = useMemo(() => {
    if (displaySt !== 'starting' && displaySt !== 'running') return null
    if (!task?.started_at) return null
    const start = new Date(task.started_at).getTime()
    const ms = now - start
    if (!Number.isFinite(ms) || ms < 0) return null
    return ms
  }, [displaySt, task?.started_at, now])

  // 20260929_容器状态动态反馈:elapsed 格式化。
  // <60s → `Ns`;≥60s → `Nm Ss`(如 12s / 5m03s);null → 不显示
  const elapsedFmt = useMemo(() => {
    if (elapsedMs === null) return null
    const s = Math.floor(elapsedMs / 1000)
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60)
    const rs = s % 60
    return `${m}m${String(rs).padStart(2, '0')}s`
  }, [elapsedMs])

  if (!task) {
    return (
      <div className="page wide page-fill">
        <div className="page-loading"><Loader2 size={16} className="animate-spin" />加载中...</div>
      </div>
    )
  }
  // vp L1465:文件树仅 dev 且非挂起显示
  const showTree = task.type === 'dev' && task.status !== 'pending'
  // BUG-UI-081(用户口径):requirement(打磨)任务面向产品,对话为主工作区 → 左右对调
  // (对话/终端/活动 移中栏占 1fr,PRD/工作区 移右栏 384px);dev/test/release 面向开发者保持现状
  const swapPanes = task.type === 'requirement'
  const tabCls = (key: CenterTab | RightTab, cur: string) => `tab${cur === key ? ' on' : ''}`

  /* ---------------- wb-head acts(vp L1462-1464 条件;R35.F3/F6 追加式) ---------------- */
  // R35.F3:failed/cancelled/timeout → 重试(useRetryTask 死代码激活,retry 后立即重新拉起)
  // R35.F6:running 恒有 停止任务;test/release 附加按钮紧随其后(原覆盖 bug 修复)
  // 20260929_任务停止页面置灰:点击停止 → 置 stopRequested 拉起遮罩;
  //   onError 撤回遮罩 + toast(沿用文件内 useToast 既有方式);
  //   遮罩期间按钮 disabled 防重复点击
  const handleStopClick = () => {
    setStopRequested(true)
    stopTask.mutate(undefined, {
      onError: (err: unknown) => {
        // 请求失败 → 撤遮罩,沿用文件内 showToast 提示
        setStopRequested(false)
        const msg = err instanceof Error ? err.message : '停止任务失败'
        showToast('err', msg)
      },
    })
  }
  // 20260929_容器重试页面置灰:点击重试 → 置 retryRequested 拉起遮罩;
  //   onError 撤回遮罩 + toast(沿用文件内 useToast 既有方式);
  //   遮罩期间按钮 disabled 防重复点击
  const handleRetryClick = () => {
    setRetryRequested(true)
    retryTask.mutate(undefined, {
      onError: (err: unknown) => {
        setRetryRequested(false)
        const msg = err instanceof Error ? err.message : '重试失败'
        showToast('err', msg)
      },
    })
  }
  // 20260929_打磨完成按钮:点击「打磨完成」→ 置 finishRequested 拉起遮罩;
  //   onSuccess 提示提交成功(PRD 已推送);onError 撤遮罩 + toast(文案回退「提交失败」);
  //   遮罩期间按钮 disabled 防重复点击
  const handleFinishClick = () => {
    setFinishRequested(true)
    finishTask.mutate(undefined, {
      onSuccess: () => {
        showToast('success', '打磨成果已提交(PRD 已推送至需求分支)')
      },
      onError: (err: unknown) => {
        setFinishRequested(false)
        const msg = err instanceof Error ? err.message : '提交失败'
        showToast('err', msg)
      },
    })
  }
  const acts: ReactNode = (
    <>
      {/* 20260929_打磨完成按钮:requirement 任务运行中时,在「停止任务」左侧 */}
      {task.type === 'requirement' && isRun && (
        <button className="btn btn-pri" onClick={handleFinishClick} disabled={finishTask.isPending || finishRequested}>
          <CheckCircle2 size={13} />{finishTask.isPending || finishRequested ? '提交中…' : '打磨完成'}
        </button>
      )}
      {isRun && (
        <button className="btn btn-danger" onClick={handleStopClick} disabled={stopRequested}>
          <Square size={13} />{stopRequested ? '停止中…' : '停止任务'}
        </button>
      )}
      {['failed', 'cancelled', 'timeout'].includes(task.status) && (
        <button className="btn" onClick={handleRetryClick} disabled={retryTask.isPending || retryRequested}>
          <RotateCcw size={13} />{retryTask.isPending || retryRequested ? '重试中…' : '重试'}
        </button>
      )}
      {task.type === 'test' && (
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
      )}
      {task.type === 'release' && (
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
      )}
    </>
  )

  /* ---------------- 中栏 centerPane 五分支(vp L1253-1377) ---------------- */

  // 公共 Tab 条(vp:tabs padding:0 10px;background:var(--surface);样式由 .wb .tabs 承接)
  // 可选 rightSlot:第三参传入时右对齐渲染在 tabs 行右端(不传时与现状完全一致)
  const tabsBar = (nodes: ReactNode, rightSlot?: ReactNode) => (
    <div className="tabs">
      {nodes}
      {rightSlot && <span className="tabs-right">{rightSlot}</span>}
    </div>
  )

  // R38:head 口径空态判定(scope==='head' && 无错误 && 0 文件 → 全部已 commit)
  const headEmpty = diffScope === 'head' && !diffError && changedFiles.length === 0
  // ---- Diff 视图(dev/test 共用;vp diff pane 结构:d-chips + 内容 + card-foot) ----
  // R38:d-chips 行右端新增口径开关(两 pill 互斥,复用 .dchip 基础,选中 .on)
  const diffView = (
    <>
      <div className="d-chips">
        {/* head 口径空态:0 文件时显示区分文案 + 切回按钮(替代 chips 列表) */}
        {headEmpty && (
          <span className="small faint">无未提交变更(全部已 commit)</span>
        )}
        {!headEmpty && changedFiles.length === 0 && <span className="small faint">暂无变更文件</span>}
        {!headEmpty && changedFiles.map((f) => {
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
        {/* R38:口径开关右端(margin-left auto 推到行尾;pill 复用 .dchip 样式基础) */}
        <span className="dchip-scope">
          <button
            type="button"
            className={`dchip${diffScope === 'all' ? ' on' : ''}`}
            onClick={() => setDiffScope('all')}
            disabled={diffFetching && diffScope === 'all'}
          >全部改动</button>
          <button
            type="button"
            className={`dchip${diffScope === 'head' ? ' on' : ''}`}
            onClick={() => setDiffScope('head')}
            disabled={diffFetching && diffScope === 'head'}
          >仅未提交</button>
        </span>
      </div>
      <div className="ed-scroll diff-body">
        {/* R4.F8(BUG-075):加载失败→可见错误条+重试,不再误导为「暂无变更」 */}
        {diffError ? (
          <div className="empty">
            Diff 数据加载失败(容器不可达或加载超时)
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => refetchDiff()}>
              <RotateCcw size={13} /> 重试
            </button>
          </div>
        ) : headEmpty ? (
          /* R38:head 口径全空→区分文案 + 切回按钮 */
          <div className="empty">
            无未提交变更(全部已 commit)
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setDiffScope('all')}>
              <RotateCcw size={13} /> 切回全部改动
            </button>
          </div>
        ) : diffPath && currentDiff() ? (
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
              {/* R4.F6(BUG-070 复开):内容加载三态——加载中/失败(带重试)/内容。
                  此前 read 失败静默渲染空编辑器,用户无法分辨「空文件」与「加载失败」 */}
              {fileContentLoading && (
                <div className="flex items-center gap-2 px-4 py-2 text-sm text-text-muted">
                  <Loader2 size={14} className="animate-spin" /> 加载文件中…
                </div>
              )}
              {!fileContentLoading && fileContentError && (
                <div className="flex items-center gap-2 px-4 py-2 text-sm text-red-500">
                  文件加载失败(容器不可达或路径无效)
                  <button type="button" className="btn btn-sm btn-ghost" onClick={() => refetchFileContent()}>
                    <RotateCcw size={13} /> 重试
                  </button>
                </div>
              )}
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

  // ---- requirement 打磨(vp L1364-1376:PRD 草稿 / 工作区) ----
  // R3:数据源切换至平台副本接口,原 reqFallbackFields 回退分支已移除(已确认 ⑤)
  const reqCenter = (
    <div className="twrap card twrap-fill">
      {tabsBar(<>
        <button className={tabCls('prd', centerTab)} onClick={() => setCenterTab('prd')}><FileText size={14} />PRD 草稿</button>
        <button className={tabCls('files', centerTab)} onClick={() => setCenterTab('files')}><FolderOpen size={14} />工作区</button>
      {/* 20260929_工作区全屏按钮统一右上角:tabs 行右端按激活 Tab 动态切换 */}
      </>, (centerTab === 'prd' || centerTab === 'files') && (
        <button
          type="button" title={centerTab === 'prd' ? 'PRD 草稿全屏' : '工作区全屏'}
          className="btn btn-sm btn-ghost icon-btn"
          onClick={() => toggleFullscreen(centerTab)}
        >
          <Maximize2 size={13} />
        </button>
      ))}
      {/* 20260929_任务打磨面板全屏:PRD 草稿 pane 支持全屏(portal 到 body 解决层叠上下文陷阱) */}
      {centerTab === 'prd' && (() => {
        const pane = (
          <>
            <div className="ed-scroll">
              <div className="card-body">
                {!req || prdContentLoading ? (
                  // R3:需求详情未就绪或 hook loading 态(沿用原「需求文档加载中…」文案)
                  <div className="empty">需求文档加载中…</div>
                ) : prdContentData?.prd_content ? (
                  // R3:平台副本非空 → markdown 全文渲染(.md 容器类沿用)
                  <div className="md" dangerouslySetInnerHTML={{ __html: renderMarkdown(prdContentData.prd_content) }} />
                ) : (
                  // R3:副本为空(容器离线/文件未产出)→ 空态引导,不报错
                  <div className="text-sm text-text-muted mb-2">暂无 PRD,完成首轮打磨后可预览</div>
                )}
              </div>
            </div>
            <div className="card-foot mt-auto">
              内容自动同步至平台 · 评审通过后才 commit 到 {task.work_branch}(评审人个人 token)
            </div>
          </>
        )
        return fullscreen === 'prd' ? (
          createPortal(
            <div className="fixed inset-0 z-[70] bg-surface p-2 flex flex-col">
              <div className="flex justify-end mb-1">
                <button
                  type="button" title="退出全屏"
                  className="btn btn-sm btn-ghost icon-btn"
                  onClick={() => toggleFullscreen('prd')}
                >
                  <Minimize2 size={13} />
                </button>
              </div>
              {pane}
            </div>,
            document.body
          )
        ) : (
          <div className="flex-1 min-h-0 flex flex-col">
            {pane}
          </div>
        )
      })()}
      {/* 20260929_任务打磨面板全屏:工作区 pane 支持全屏(portal 到 body 解决层叠上下文陷阱) */}
      {centerTab === 'files' && (() => {
        const pane = (
          <>
            <div className="ed-scroll">
              <div className="tree">
                <div className="tnode dir"><FolderOpen size={14} /><span className="nm mono">/workspace/main</span></div>
                {/* BUG-070 R4.F6:懒加载文件树(与开发任务「全部文件」Tab 同参同行为)——
                    rootPath 绝对路径基准 + loadDir 目录懒加载 + refreshNonce 外部刷新。
                    R39:打磨布局无编辑器 pane,点文件不切 'edit'(会两分支皆空白),
                    改为树下只读预览(见下方 file-preview) */}
                <FileTree
                  mode="task"
                  files={filesData?.items ?? []}
                  rootPath="/workspace/main"
                  loadDir={loadTaskDir}
                  refreshNonce={treeRefreshNonce}
                  selectedPath={selectedPath}
                  onSelectFile={(p) => { setSelectedPath(p); setEnabled(true) }}
                  onRefresh={refreshFileTree}
                  isRefreshing={filesFetching}
                />
                {(filesData?.items ?? []).length === 0 && <div className="empty">容器暂无文件</div>}
                {/* R39:打磨任务文件只读预览(树下方;三态与编辑器 pane 同源同款) */}
                {selectedPath && enabled && (
                  <div className="file-preview">
                    <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
                      <FileText size={13} className="flex-shrink-0" />
                      <span className="mono text-xs truncate flex-1" title={selectedPath}>{selectedPath}</span>
                      <button type="button" className="btn btn-sm btn-ghost icon-btn" title="关闭预览"
                        onClick={() => { setSelectedPath(''); setEditorDraft(null) }}>
                        ×
                      </button>
                    </div>
                    {fileContentLoading && (
                      <div className="flex items-center gap-2 px-3 py-2 text-sm text-text-muted">
                        <Loader2 size={14} className="animate-spin" /> 加载文件中…
                      </div>
                    )}
                    {!fileContentLoading && fileContentError && (
                      <div className="flex items-center gap-2 px-3 py-2 text-sm text-red-500">
                        文件加载失败(容器不可达或路径无效)
                        <button type="button" className="btn btn-sm btn-ghost" onClick={() => refetchFileContent()}>
                          <RotateCcw size={13} /> 重试
                        </button>
                      </div>
                    )}
                    {!fileContentLoading && !fileContentError && (
                      <pre className="mono" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', fontSize: 12, lineHeight: 1.6, padding: '10px 12px', margin: 0 }}>
                        {fileData?.content ?? ''}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            </div>
            <div className="card-foot mt-auto">
              工作区文件 · 只读预览(编辑请到编辑器 pane)
            </div>
          </>
        )
        return fullscreen === 'files' ? (
          createPortal(
            <div className="fixed inset-0 z-[70] bg-surface p-2 flex flex-col">
              <div className="flex justify-end mb-1">
                <button
                  type="button" title="退出全屏"
                  className="btn btn-sm btn-ghost icon-btn"
                  onClick={() => toggleFullscreen('files')}
                >
                  <Minimize2 size={13} />
                </button>
              </div>
              {pane}
            </div>,
            document.body
          )
        ) : (
          <div className="flex-1 min-h-0 flex flex-col">
            {pane}
          </div>
        )
      })()}
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
          taskType={task.type}
          prdFilePath={req?.prd_file_path || ''}
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
              {/* 20260929_容器状态动态反馈:starting 时徽章前加 Loader2 spinner(加载中视觉反馈) */}
              {displaySt === 'starting' && <Loader2 size={13} className="animate-spin" />}
              <StatusBadge status={displaySt} pulse={isRun} />
              {/* 20260929_容器状态动态反馈:starting/running 时徽章后追加时间 chip(已等多久/运行多久) */}
              {elapsedFmt && (
                <span className="small muted mono">· {elapsedFmt}</span>
              )}
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
                  rootPath="/workspace/main"
                  loadDir={loadTaskDir}
                  refreshNonce={treeRefreshNonce}
                  isRefreshing={filesFetching}
                  changes={changesData?.repos ?? []}
                  selectedPath={selectedPath}
                  onSelectFile={(p) => { setSelectedPath(p); setEnabled(true); setCenterTab('edit') }}
                  onSelectDiff={(p) => { setDiffPath(p); setCenterTab('diff') }}
                  onRefresh={refreshFileTree}
                />
              </div>
              {/* R39:git 操作行(tree-foot 之上一行;card-foot 样式)
                  条件渲染:editor+(owner/editor) 且任务 running;viewer 或终态任务不渲染 */}
              {showTree && isRun && (myRole === 'owner' || myRole === 'editor') && (
                <div className="card-foot" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderTop: '1px solid #e4e4e7' }}>
                  <span style={{ display: 'flex', gap: 6 }}>
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={gitCommit.isPending || gitPush.isPending}
                      onClick={handleCommitClick}
                    >
                      <GitCommit size={13} />提交
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={gitCommit.isPending || gitPush.isPending}
                      onClick={handlePushClick}
                    >
                      <Upload size={13} />推送
                    </button>
                  </span>
                  <small style={{ color: '#71717a', fontSize: 13 }}>
                    身份:{identityName} &lt;{identityEmail}&gt;
                  </small>
                </div>
              )}
              {/* tree-foot(vp L1238-1243;字段映射真实任务) */}
              <div className="tree-foot">
                <span><b>容器</b> {task.container_id ? `${task.container_id.slice(0, 7)} · devbox:v2` : '—'}</span>
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
      {/* 20260929_任务停止页面置灰:全页遮罩(条件 = stopRequested)
          复用 globals.css .page-blocking-overlay(fixed inset-0 / z-70 / 半透明灰底 / 拦截点击)
          遮罩期间停止按钮已 disabled,此处再包一层视觉反馈 */}
      {stopRequested && (
        <div className="page-blocking-overlay">
          <Loader2 size={32} className="animate-spin" />
          <div className="text-sm text-white/80">正在停止容器…</div>
        </div>
      )}
      {/* 20260929_容器重试页面置灰:全页遮罩(条件 = retryRequested)
          与停止遮罩同款复用 globals.css .page-blocking-overlay,文案区分 */}
      {retryRequested && (
        <div className="page-blocking-overlay">
          <Loader2 size={32} className="animate-spin" />
          <div className="text-sm text-white/80">正在启动容器…</div>
        </div>
      )}
      {/* 20260929_任务容器未启动置灰引导:容器门卫遮罩
          条件:containerGateStarting(正在启动中,轮询到 running 自动撤)
          复用 .page-blocking-overlay,与停止/重试遮罩同级 z-index;
          若与停止遮罩交叉(极端轮询间隙),停止遮罩优先(渲染顺序在后) */}
      {containerGateStarting && (
        <div className="page-blocking-overlay">
          <Loader2 size={32} className="animate-spin" />
          <div className="text-sm text-white/80">容器启动中…</div>
        </div>
      )}
      {/* 20260929_任务容器未启动置灰引导:容器门卫弹框
          条件:containerGateOpen(非 running/starting + 未跳过)
          使用 ui/Dialog 组件,文案「任务容器未启动,是否启动容器」
          按钮:「启动」(primary)/「暂不」(次要)
          pending 态「启动」按钮 disabled + toast 提示「排队任务等待调度」 */}
      {containerGateOpen && (
        <Dialog open={containerGateOpen} onOpenChange={setContainerGateOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>任务容器未启动</DialogTitle>
            </DialogHeader>
            <div style={{ padding: '16px 0', fontSize: 14, color: 'var(--text-muted, #71717a)' }}>
              是否启动容器?
            </div>
            <DialogFooter>
              {/* 20260929 按钮样式统一:暂不→次按钮(默认 .btn,灰底);启动→主按钮 .btn-pri(站点统一主色 var(--primary)) */}
              <button
                type="button"
                className="btn"
                onClick={handleContainerGateSkip}
              >
                暂不
              </button>
              <button
                type="button"
                className="btn btn-pri"
                disabled={retryTask.isPending || (task?.display_status ?? task?.status) === 'pending'}
                onClick={handleContainerGateStart}
              >
                {retryTask.isPending ? '启动中…' : '启动'}
              </button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {/* R39:commit Dialog — 提交变更弹窗 */}
      {showTree && isRun && (myRole === 'owner' || myRole === 'editor') && (
        <Dialog open={commitDialogOpen} onOpenChange={setCommitDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>提交变更到 {task.work_branch}</DialogTitle>
            </DialogHeader>
            <div style={{ padding: '16px 0' }}>
              <label style={{ display: 'block', marginBottom: 8, fontSize: 14, fontWeight: 500 }}>
                提交信息
              </label>
              <textarea
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                placeholder={defaultCommitMessage}
                disabled={gitCommit.isPending}
                rows={4}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #d4d4d9',
                  borderRadius: 6,
                  fontSize: 14,
                  resize: 'vertical',
                  fontFamily: 'inherit',
                }}
              />
            </div>
            <DialogFooter>
              <button
                type="button"
                className="btn"
                disabled={gitCommit.isPending}
                onClick={() => setCommitDialogOpen(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="btn btn-pri"
                disabled={gitCommit.isPending}
                onClick={handleCommitConfirm}
              >
                {gitCommit.isPending ? '提交中…' : '确认提交'}
              </button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
      {ToastEl}
    </BreadcrumbOverrideProvider>
  )
}
