/**
 * TaskChat — 任务对话框
 * - 消息列表(user 右侧/assistant 左侧气泡,@filename 渲染为链接)
 * - 输入框(@ 触发已上传文件补全;R32.F2:/ 触发项目已装 Skills 补全)
 * - R7:/skills 候选合并系统级(镜像内置,同名项目配置优先,「内置」徽标仅插入引用)
 * - R7:/mcp 补全(项目 MCP 配置 ∪ 系统级,选中插入 @mcp:名称)
 * - R32.F3:流式输出(发送中 AI 气泡逐字增量,经任务事件 WS chat_delta)
 * - 附件按钮(Paperclip,提示"上传文件")+ 拖拽上传
 * - 附件列表(文件名点击下载,X 删除)
 * - 发送按钮"发送"
 * - R34:聊天气泡优化(20260927_AI对话框气泡优化):AI 气泡 markdown 渲染(@filename
 *   占位符链接保留下载)/ 元信息行(HH:MM + hover 操作栏:复制/重新生成/引用回复)/
 *   流式呼吸圆点 .chat-cursor-dot + 停止生成 / 空态快捷指令 / 发送失败乐观保留可重试 /
 *   补全下拉键盘导航(ArrowUp/Down 循环 + Enter 选中,skill 引用格式 @→/)
 * - R34:头像布局(20260927 头像布局.md)——头像+昵称行(.chat-head)移到消息上方,
 *   用户头像取 auth store 当前用户(占位,待后端 TaskMessage sender 字段做多用户逐人头像)
 * - R34.F1(BUG-UI-090):「停止生成」按钮整个发送 pending 期间常显(流式增量前也有停止入口);
 *   点击接线后端真取消 POST /tasks/{id}/messages/cancel,stoppedRef 展示层中止保留为兜底
 * - R34.F2(BUG-UI-092):输入区模型切换下拉(项目启用中的模型配置,默认选 is_default;
 *   发送请求体携带 config_id——后端消费待契约,占位)
 * - R34.F3(BUG-UI-091):AI 权限确认卡 —— WS chat_confirm_request 在消息列表尾部
 *   插入确认区块(prompt + 允许/拒绝),应答 POST /tasks/{id}/confirm 后转
 *   「已允许/已拒绝/已超时拒绝」灰态;chat_confirm_resolved(超时/停止收口)同步灰态;
 *   挂起期间停止按钮仍可点(stop 优先,确认随收口转「已拒绝」)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Check, ChevronDown, Copy, Download, Loader2, Maximize2, Minimize2, Paperclip, Plug,
  Quote, RefreshCw, Send, Sparkles, Square, X,
} from 'lucide-react'
import { renderMarkdown } from '@/utils/markdown'
import { useAuthStore } from '@/stores/authStore'
import { Avatar } from './ui/Avatar'
import { Button } from './ui/Button'
import { OrangeMark } from './OrangeMark'
import {
  useTaskMessages, useSendTaskMessage, useUploadTaskFile,
  useUploadedFiles, useDeleteTaskFile, downloadTaskFile,
  cancelTaskMessage, getTaskErrorMessage, useTaskChatStream,
  confirmTaskToolUse,
} from '@/api/tasks'
import type {
  TaskMessage, UploadedFile,
  ChatConfirmRequestEvent, ChatConfirmResolvedEvent,
} from '@/api/tasks'
import { mcpApi, skillsApi, systemAssetsApi, type McpConfig, type Skill, type SystemAssetsData } from '@/api/skills'
import { modelConfigsApi, type ModelConfig } from '@/api/projects'
import { ApiError } from '@/api/client'

interface TaskChatProps {
  taskId: string
  /** 全屏(BUG-UI-064:CSS 提升为 fixed 覆盖层,组件不重挂载,消息与输入态保留) */
  fullscreen?: boolean
  onToggleFullscreen?: () => void
  /** R32.F2:项目 ID(有值时启用 / skill 补全,数据源为项目已装 Skills) */
  projectId?: string
}

// 渲染消息内容 — 把 @filename 渲染为可点击链接
function renderContent(content: string, files: UploadedFile[]) {
  const parts: Array<string | { filename: string }> = []
  const regex = /@(\S+)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = regex.exec(content))) {
    if (m.index > last) parts.push(content.slice(last, m.index))
    parts.push({ filename: m[1] })
    last = m.index + m[0].length
  }
  if (last < content.length) parts.push(content.slice(last))

  return parts.map((p, i) => {
    if (typeof p === 'string') return <span key={i}>{p}</span>
    const hit = files.find((f) => f.filename === p.filename)
    if (hit) {
      return (
        <a
          key={i}
          className="text-primary underline mx-0.5"
          href={`/api/tasks/files/uploads/${hit.file_id}`}
          onClick={(e) => {
            e.preventDefault()
            // 触发下载
            downloadTaskFile('', hit.file_id).then((blob) => {
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = hit.filename
              a.click()
              URL.revokeObjectURL(url)
            })
          }}
        >
          @{hit.filename}
        </a>
      )
    }
    return <span key={i}>@{p.filename}</span>
  })
}

/* R34:聊天气泡优化(20260927_AI对话框气泡优化)—— AI 气泡 markdown 渲染 */
// 渲染前把 @filename 替换为占位符 ⟦@name⟧(防 markdown 转义/行内标记破坏文件名),
// renderMarkdown 输出后再把占位符替换为下载链接(占位符经 escapeHtml 后 ⟦⟧ 原样存活,
// 仅捕获段可能带 &amp; 等实体,比较前反解)。围栏/行内代码内的 @ 引用同样成链,与原
// renderContent 简单解析同粒度,不另做作用域排除。
const AT_PH_RE = /⟦@([^⟧]*)⟧/g
function renderAiHtml(content: string, files: UploadedFile[]) {
  const unesc = (s: string) =>
    s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&')
  const esc = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  const html = renderMarkdown(content.replace(/@(\S+)/g, (_m, name: string) => `⟦@${name}⟧`))
  return html.replace(AT_PH_RE, (_m, rawName: string) => {
    const name = unesc(rawName)
    const hit = files.find((f) => f.filename === name)
    if (!hit) return `@${esc(name)}`
    return `<a class="chat-file-link" data-file-id="${esc(hit.file_id)}" href="/api/tasks/files/uploads/${esc(hit.file_id)}">@${esc(hit.filename)}</a>`
  })
}

// R34:HH:MM 时间戳(created_at 缺失/非法时本地时间兜底——占位口径,后端字段恒有值)
function formatTime(iso?: string): string {
  const d = iso ? new Date(iso) : new Date()
  if (isNaN(d.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}`
}

export function TaskChat({ taskId, fullscreen = false, onToggleFullscreen, projectId }: TaskChatProps) {
  const { data: msgData } = useTaskMessages(taskId)
  const { data: uploadsData, refetch: refetchUploads } = useUploadedFiles(taskId)
  const sendMut = useSendTaskMessage(taskId)
  const uploadMut = useUploadTaskFile(taskId)
  const deleteMut = useDeleteTaskFile(taskId)

  const [input, setInput] = useState('')
  const [showAC, setShowAC] = useState(false)
  const [acIndex, setAcIndex] = useState(0)
  // R32.F2:/ skill 补全(与 @ 文件补全互斥)
  const [showSC, setShowSC] = useState(false)
  const [scIndex, setScIndex] = useState(0)
  const [skills, setSkills] = useState<Skill[]>([])
  // R7:/mcp 补全(与 / skills 补全同模式互斥)
  const [showMC, setShowMC] = useState(false)
  const [mcIndex, setMcIndex] = useState(0)
  // R7:项目 MCP 配置 + 系统级资产快照(/skills、/mcp 候选合并;未采集/异常回退现状)
  const [mcpServers, setMcpServers] = useState<McpConfig['config']['mcpServers']>({})
  const [sysAssets, setSysAssets] = useState<SystemAssetsData | null>(null)
  // R32.F3:流式增量(发送中的 AI 气泡文本;chat_done 或消息落库后清空)
  const [streamText, setStreamText] = useState('')
  // R32.F9:乐观 UI——用户消息发送即上屏(pendingUser)+ AI 加载动效(thinking,首个增量前)
  const [pendingUser, setPendingUser] = useState<string | null>(null)
  const [thinking, setThinking] = useState(false)
  // R34:发送失败的用户消息乐观保留(红描边气泡 + 「发送失败 · 点击重试」)
  const [failedUser, setFailedUser] = useState<string | null>(null)
  // R34.F3(BUG-UI-091):AI 权限确认卡 —— null=无;status 状态机:
  // pending(挂起,按钮可点)→ allow/deny(用户应答,乐观灰态)/ timeout(超时收口灰态);
  // 服务端保证单任务同一时刻至多 1 个待确认,新请求直接覆盖旧卡
  const [confirmCard, setConfirmCard] = useState<{
    confirmId: string
    prompt: string
    status: 'pending' | 'allow' | 'deny' | 'timeout'
  } | null>(null)
  // R34.F2(BUG-UI-092):模型切换 —— 项目启用中的模型配置 + 当前选中(组件级会话记忆,
  // 刷新回默认);无 projectId / 无启用配置时两者皆空,切换器不渲染
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([])
  const [selectedConfigId, setSelectedConfigId] = useState<string | null>(null)
  const [showModelDD, setShowModelDD] = useState(false)
  // R34:操作栏「已复制」反馈(按 message_id 记录,1.5s 复位)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // R34:文本输入框 ref(引用回复/快捷指令填入后聚焦)
  const inputRef = useRef<HTMLInputElement>(null)
  // R34:复制反馈复位定时器(卸载清理)
  const copyTimerRef = useRef<number | null>(null)
  // R34(BUG-UI-086):停止生成闸阀——置 true 后 onDelta 丢弃后续增量(展示层中止),
  // 新一轮 handleSend 复位;用 ref 而非 state,避免 WS 高频回调闭包读到旧值
  const stoppedRef = useRef(false)
  // R34(补全键盘导航):三组下拉高亮项 ref(scrollIntoView 用)
  const activeACRef = useRef<HTMLButtonElement | null>(null)
  const activeSCRef = useRef<HTMLButtonElement | null>(null)
  const activeMCRef = useRef<HTMLButtonElement | null>(null)

  const messages: TaskMessage[] = msgData?.items ?? []
  const files: UploadedFile[] = uploadsData?.items ?? []

  // R34.F2:当前选中的模型配置(选中项失效时回退默认项/首个,兜底 undefined 不渲染名称)
  const currentModelConfig =
    modelConfigs.find((c) => c.config_id === selectedConfigId) ??
    modelConfigs.find((c) => c.is_default) ??
    modelConfigs[0]

  // R32.F2:项目已装 Skills(仅 projectId 就绪时拉一次)
  useEffect(() => {
    if (!projectId) return
    skillsApi.installed(projectId)
      .then((d) => setSkills(d.data?.items ?? []))
      .catch(() => setSkills([]))
  }, [projectId])

  // R34.F2(BUG-UI-092):项目模型配置(仅 enabled;默认选中 is_default 项,无默认取首个;
  // 拉取失败按无配置回退 → 切换器不渲染)
  useEffect(() => {
    if (!projectId) return
    modelConfigsApi.list(projectId)
      .then((res) => {
        const items = (res.data?.items ?? []).filter((c) => c.enabled)
        setModelConfigs(items)
        setSelectedConfigId((items.find((c) => c.is_default) ?? items[0])?.config_id ?? null)
      })
      .catch(() => {
        setModelConfigs([])
        setSelectedConfigId(null)
      })
  }, [projectId])

  // R7:项目 MCP 配置(未配置 → {config:null} 按空)+ 系统级资产快照(失败/未采集按 null 回退现状)
  useEffect(() => {
    if (!projectId) return
    mcpApi.get(projectId)
      .then((d) => setMcpServers(d.data?.config?.mcpServers ?? {}))
      .catch(() => setMcpServers({}))
    systemAssetsApi.get()
      .then((d) => setSysAssets(d.data ?? null))
      .catch(() => setSysAssets(null))
  }, [projectId])

  // R32.F3:订阅 chat_delta / chat_done(事件 WS;发送中逐字上屏)
  // R32.F9:onDone 不再清 streamText——保留全文气泡直到 POST onSuccess 刷新消息后
  // 统一清理,避免「流式气泡消失但真消息尚未刷新」的闪空
  useTaskChatStream(taskId, {
    onDelta: (text) => {
      // BUG-UI-086:停止生成后丢弃增量(展示层中止),否则下一条 delta 会把气泡填回来
      if (stoppedRef.current) return
      setThinking(false)
      setStreamText((prev) => prev + text)
    },
    onDone: () => setThinking(false),
    // R34.F3:确认请求 → 尾部确认卡(挂起);服务端单任务串行执行保证同时至多 1 个待确认
    onConfirmRequest: (evt: ChatConfirmRequestEvent) => {
      setConfirmCard({ confirmId: evt.confirm_id, prompt: evt.prompt, status: 'pending' })
    },
    // R34.F3:超时/停止收口 → 灰态(timeout=「已超时拒绝」,stopped=「已拒绝」)。
    // 用户自己应答后端不广播 resolved(本地乐观灰态已覆盖);超时与应答竞态时
    // resolved 后到,以此帧为准覆盖乐观态
    onConfirmResolved: (evt: ChatConfirmResolvedEvent) => {
      setConfirmCard((prev) =>
        prev && prev.confirmId === evt.confirmId
          ? { ...prev, status: evt.reason === 'timeout' ? 'timeout' : 'deny' }
          : prev,
      )
    },
  })

  // R32.F9:自动滚动到底——新消息/乐观上屏/加载动效/流式增量任一变化都平滑滚到最新,
  // 不再需要手动往下滚(原实现只盯 messages.length/streamText,乐观消息与动效不触发)
  // R34.F3:确认卡出现/转灰态同样滚到底(卡在列表尾部,不滚则首屏外不可见)
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages.length, pendingUser, thinking, streamText, failedUser, confirmCard])

  // toast 自动消失
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 2500)
    return () => clearTimeout(t)
  }, [toast])

  // R34:@filename 下载链接点击 —— 消息列表容器事件委托(历史/流式 markdown 气泡统一;
  // renderMarkdown 输出的 <a class="chat-file-link"> 无法携带 React onClick)
  useEffect(() => {
    const el = listRef.current
    if (!el) return
    const onClick = (e: MouseEvent) => {
      const link = (e.target as HTMLElement).closest('a.chat-file-link') as HTMLAnchorElement | null
      if (!link) return
      e.preventDefault()
      const hit = files.find((f) => f.file_id === link.dataset.fileId)
      if (!hit) return
      downloadTaskFile('', hit.file_id).then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = hit.filename
        a.click()
        URL.revokeObjectURL(url)
      })
    }
    el.addEventListener('click', onClick)
    return () => el.removeEventListener('click', onClick)
  }, [files])

  // R34(补全键盘导航):高亮项滚动进可视区(高亮 ref 挂在当前选中按钮上;block:nearest 不扰动容器)
  useEffect(() => {
    if (showAC) activeACRef.current?.scrollIntoView({ block: 'nearest' })
    else if (showSC) activeSCRef.current?.scrollIntoView({ block: 'nearest' })
    else if (showMC) activeMCRef.current?.scrollIntoView({ block: 'nearest' })
  }, [showAC, showSC, showMC, acIndex, scIndex, mcIndex])

  // R34:复制反馈定时器卸载清理
  useEffect(() => () => {
    if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current)
  }, [])

  const showToast = (type: 'ok' | 'err', text: string) => setToast({ type, text })

  // 上传文件
  const handleUpload = useCallback(async (file: File) => {
    try {
      await uploadMut.mutateAsync(file)
      showToast('ok', '上传成功')
      refetchUploads()
    } catch (err) {
      const code = err instanceof ApiError ? err.code : 0
      showToast('err', getTaskErrorMessage(code, '上传失败,请重试'))
    }
  }, [uploadMut, refetchUploads])

  // 拖拽上传
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const fileList = e.dataTransfer.files
    for (let i = 0; i < fileList.length; i++) handleUpload(fileList[i])
  }, [handleUpload])

  // @ 文件补全 + / skill 补全 + /mcp 补全(R32.F2/R7;三者互斥,以末尾触发符为准;
  // /mcp 先于 / 判定——/mcp 前缀归 MCP 候选,其余 / 归 Skill 候选)
  const handleInputChange = (v: string) => {
    setInput(v)
    if (v.match(/@(\S*)$/)) {
      setShowAC(true); setAcIndex(0); setShowSC(false); setShowMC(false)
    } else if (projectId && v.match(/(?:^|\s)\/mcp(\S*)$/)) {
      setShowMC(true); setMcIndex(0); setShowSC(false); setShowAC(false)
    } else if (projectId && v.match(/(?:^|\s)\/(\S*)$/)) {
      setShowSC(true); setScIndex(0); setShowAC(false); setShowMC(false)
    } else {
      setShowAC(false); setShowSC(false); setShowMC(false)
    }
  }

  const selectAC = (filename: string) => {
    const replaced = input.replace(/@\S*$/, `@${filename} `)
    setInput(replaced)
    setShowAC(false)
  }

  // R32.F2:选中 skill → 输入框插入 skill 引用(空格结尾)
  // R34(补全键盘导航):引用格式 @skill名 → /skill名(规范 2026-09-27 补充);
  // 待开发支持清单:skill 引用格式 @→/,需确认 CLI 侧解析兼容(@mcp: 格式保持不变)
  const selectSC = (skillName: string) => {
    const replaced = input.replace(/\/(\S*)$/, `/${skillName} `)
    setInput(replaced)
    setShowSC(false)
  }

  // R7:选中 MCP → 插入 @mcp:名称(与 @skill 引用同交互形态)
  const selectMC = (mcpName: string) => {
    const replaced = input.replace(/\/mcp\S*$/, `@mcp:${mcpName} `)
    setInput(replaced)
    setShowMC(false)
  }

  const filteredFiles = files.filter((f) => {
    const atMatch = input.match(/@(\S*)$/)
    if (!atMatch) return false
    return f.filename.toLowerCase().includes(atMatch[1].toLowerCase())
  })

  // R7:/skills 候选 = 项目已装 ∪ 系统内置(同名项目配置优先;未采集 collected:false → 回退现状仅项目项)
  const projectSkillNames = new Set(skills.map((s) => s.name))
  const mergedSkills: Array<{ name: string; description: string; builtin: boolean }> = [
    ...skills.map((s) => ({ name: s.name, description: s.description, builtin: false })),
    ...(sysAssets?.collected ? sysAssets.skills ?? [] : [])
      .filter((s) => !projectSkillNames.has(s.name))
      .map((s) => ({ name: s.name, description: '', builtin: true })),
  ]

  // R7:/mcp 候选 = 项目 MCP 配置(mcpServers 键)∪ 系统级(内置;同名项目配置优先)
  const mcpCandidates: Array<{ name: string; hint: string; builtin: boolean }> = [
    ...Object.entries(mcpServers).map(([name, cfg]) => ({
      name,
      hint: typeof cfg.command === 'string' ? cfg.command : '',
      builtin: false,
    })),
    ...(sysAssets?.collected ? sysAssets.mcps ?? [] : [])
      .filter((m) => !(m.name in mcpServers))
      .map((m) => ({
        name: m.name,
        // hint 只取 command/transport,不透传 args/env(防探测原文里的连接串进对话)
        hint: typeof m.detail.command === 'string'
          ? m.detail.command
          : typeof m.detail.transport === 'string' ? m.detail.transport : '',
        builtin: true,
      })),
  ]

  const filteredSkills = mergedSkills.filter((s) => {
    const slashMatch = input.match(/(?:^|\s)\/(\S*)$/)
    if (!slashMatch) return false
    return s.name.toLowerCase().includes(slashMatch[1].toLowerCase())
  })

  const filteredMcps = mcpCandidates.filter((m) => {
    const mcpMatch = input.match(/(?:^|\s)\/mcp(\S*)$/)
    if (!mcpMatch) return false
    return m.name.toLowerCase().includes(mcpMatch[1].toLowerCase())
  })

  // R32.F9:乐观发送——输入即清、用户消息秒上屏、AI 气泡先出加载动效;
  // 增量到达后由流式气泡接管,POST 返回刷新消息后统一收口。POST 未返回前禁止重复发送
  // R34:override 入参(重新生成/失败重试复用同一乐观 UI/流式链路);
  // 发送失败不再只 toast —— 乐观气泡保留(failedUser 红描边 + meta 行点击重试)
  const handleSend = (override?: string) => {
    const trimmed = (override ?? input).trim()
    if (!trimmed || sendMut.isPending) return
    stoppedRef.current = false // BUG-UI-086:新一轮发送复位停止闸阀
    setInput('')
    setPendingUser(trimmed)
    setThinking(true)
    setStreamText('')
    setConfirmCard(null) // R34.F3:上一轮确认卡(灰态)随新一轮发送移出列表尾部
    // R34.F2:携带当前选中的模型配置 configId(未选/无配置时为 undefined,请求体省略 config_id;
    // config_id 后端消费待契约(占位))
    sendMut.mutate(
      { content: trimmed, configId: selectedConfigId ?? undefined },
      {
        onSuccess: () => {
          setPendingUser(null)
          setThinking(false)
          setStreamText('')
        },
        onError: (err) => {
          setPendingUser(null)
          setThinking(false)
          setStreamText('')
          setFailedUser(trimmed)
          const code = err instanceof ApiError ? err.code : 0
          showToast('err', getTaskErrorMessage(code, '发送失败'))
        },
      },
    )
  }

  // R34:填入输入框并聚焦(快捷指令/引用回复共用;不直接发送,顺带关闭三组补全下拉)
  const fillInput = (v: string) => {
    setInput(v)
    setShowAC(false); setShowSC(false); setShowMC(false)
    inputRef.current?.focus()
  }

  // R34:引用回复 —— BUG-UI-087:① input 单行 value 会剥换行,引文压平为单行、
  // 以尾随空格与续写内容分隔;② 前置拼接到已有输入前(setInput 函数式,不覆盖丢弃)
  const handleQuote = (content: string) => {
    const quote = `> ${content.replace(/\s+/g, ' ').trim().slice(0, 200)} `
    setShowAC(false); setShowSC(false); setShowMC(false)
    setInput((prev) => quote + prev)
    inputRef.current?.focus()
  }

  // R34:复制原文(user 原样 / AI markdown 源文本),成功 Copy→Check 1.5s,失败 toast
  const handleCopy = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(id)
      if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current)
      copyTimerRef.current = window.setTimeout(() => setCopiedId(null), 1500)
    } catch {
      showToast('err', '复制失败')
    }
  }

  // R34:重新生成 —— 取指定 AI 消息之前最近一条 user 消息内容重发(handleSend 乐观链路;
  // 仅最后一条 AI 消息展示入口;发送中由 handleSend 的 isPending 守卫兜底)
  const handleRegenerate = (aiIdx: number) => {
    for (let i = aiIdx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        handleSend(messages[i].content)
        return
      }
    }
  }

  // R34:停止生成 —— 展示层中止兜底:置停止闸阀(BUG-UI-086,onDelta 入口短路丢增量)
  // + 清流式文本/加载态(同步先行,接口失败也保证生效)
  // R34.F1:接线后端真取消 —— POST /tasks/{id}/messages/cancel(容器内 pkill claude,
  // 幂等:无在途 cancelled=false 非错误);失败(网络/无容器 400 等)仅 toast 提示,不影响兜底
  const handleStopGeneration = () => {
    stoppedRef.current = true
    setStreamText('')
    setThinking(false)
    cancelTaskMessage(taskId).catch((err) => {
      const code = err instanceof ApiError ? err.code : 0
      showToast('err', getTaskErrorMessage(code, '停止请求失败'))
    })
  }

  // R34.F3:确认卡应答 —— 点击即乐观转灰态(按钮同帧禁用,天然防重复提交),
  // POST /tasks/{id}/confirm 放行执行。4001(已超时/已随停止收口/重复)→ 转
  // 「已超时拒绝」灰态兜底(WS resolved 帧若后到会以精确 reason 覆盖);其余失败
  // (网络/403)→ 回到 pending 允许重试。注意 4001 文案自带,不走共享错误映射
  // (该码在映射表里是需求状态语义)。挂起期间停止按钮不受影响(stop 优先,
  // 后端 cleanup 先广播 resolved{stopped} 再 chat_done,卡片照常收口)
  const handleConfirm = (choice: 'allow' | 'deny') => {
    if (!confirmCard || confirmCard.status !== 'pending') return
    const { confirmId } = confirmCard
    setConfirmCard((prev) => (prev && prev.confirmId === confirmId ? { ...prev, status: choice } : prev))
    confirmTaskToolUse(taskId, confirmId, choice)
      .then(() => showToast('ok', choice === 'allow' ? '已允许,继续执行' : '已拒绝'))
      .catch((err) => {
        const code = err instanceof ApiError ? err.code : 0
        setConfirmCard((prev) => {
          if (!prev || prev.confirmId !== confirmId || prev.status !== choice) return prev
          return code === 4001 ? { ...prev, status: 'timeout' } : { ...prev, status: 'pending' }
        })
        showToast('err', code === 4001 ? '确认请求已失效(超时或已收口)' : '确认失败,请重试')
      })
  }

  const handleDownload = async (f: UploadedFile) => {
    try {
      const blob = await downloadTaskFile(taskId, f.file_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = f.filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      showToast('err', '下载失败')
    }
  }

  const handleDelete = (fileId: string) => {
    deleteMut.mutate(fileId, {
      onSuccess: () => showToast('ok', '已删除'),
      onError: (err) => {
        const code = err instanceof ApiError ? err.code : 0
        showToast('err', getTaskErrorMessage(code, '删除失败'))
      },
    })
  }

  // 导出对话记录(BUG-UI-064:transcript 转 Markdown 下载)
  const handleExport = () => {
    if (messages.length === 0) return
    const md = messages
      .map((m) => `**${m.role === 'user' ? '用户' : 'AI'}**\n\n${m.content}`)
      .join('\n\n---\n\n')
    const blob = new Blob([`# 任务对话记录 ${taskId}\n\n${md}\n`], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `chat-${taskId.slice(0, 8)}.md`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  // R34:AI 侧消息 markdown HTML 缓存(useMemo,输入敲键等无关重渲染不重复解析;
  // 依赖 messages/files——消息 3s 轮询换引用时才重算)
  const aiHtmlMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const m of messages) {
      if (m.role !== 'user') map[m.message_id] = renderAiHtml(m.content, files)
    }
    return map
  }, [messages, files])
  // R34:流式增量 markdown 渲染缓存(依赖 streamText,逐字增量重渲染;未闭合围栏 markdown.ts 降级安全)
  const streamHtml = useMemo(() => renderAiHtml(streamText, files), [streamText, files])

  // R34:最后一条 AI 消息下标(操作栏「重新生成」仅挂这一条)
  let lastAiIndex = -1
  messages.forEach((m, i) => {
    if (m.role === 'assistant') lastAiIndex = i
  })

  // R34:空态快捷指令(点击填入输入框+聚焦,不直接发送)
  const SUGGESTIONS = ['帮我审查代码', '解释这个文件的实现', '生成单元测试']

  // R34(头像布局):消息头 .chat-head 行内容(头像 20px + 昵称),置于消息上方、气泡不再带侧边头像
  // 用户侧:当前用户头像/昵称 —— 占位,待后端 TaskMessage 增加 sender 字段(多用户对话逐人头像)
  const me = useAuthStore((s) => s.user)
  const userHead = (
    <>
      <Avatar src={me?.avatar_url ?? null} alt={me?.nickname ?? ''} size={20} className="shrink-0" />
      <span>{me?.nickname || '我'}</span>
    </>
  )
  // AI 侧:OrangeMark 14px(20px 品牌深色圆底,与侧栏/favicon 同识别,2026-09-27 logo 重绘)+「旗橙 AI」,身份固定
  const aiHead = (
    <>
      <span
        className="shrink-0 w-5 h-5 rounded-full bg-[#18181B] flex items-center justify-center"
        title="旗橙 AI"
      >
        <OrangeMark size={14} />
      </span>
      <span>旗橙 AI</span>
    </>
  )

  return (
    <div
      className={`flex flex-col w-full h-full min-h-0 border border-border rounded-md bg-background${fullscreen ? ' fixed inset-0 z-[60] p-2 rounded-none' : ''}`}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      {/* 面板头:标题 + 导出 + 全屏(BUG-UI-064) */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border shrink-0">
        <span className="text-sm font-medium text-text">AI 对话</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            title="导出对话记录"
            className="p-1 text-text-secondary hover:text-primary disabled:opacity-40"
            disabled={messages.length === 0}
            onClick={handleExport}
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            type="button"
            title={fullscreen ? '退出全屏' : '全屏'}
            className="p-1 text-text-secondary hover:text-primary"
            onClick={onToggleFullscreen}
          >
            {fullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* 消息列表(R34:消息间距 space-y-4) */}
      <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto p-3 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-text-secondary text-sm py-8">
            暂无消息,发送第一条指令开始任务
            {/* R34:空态快捷指令(填入输入框+聚焦,不直接发送) */}
            <div className="flex justify-center flex-wrap gap-2 mt-3">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="chat-suggest" onClick={() => fillInput(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, idx) => {
          const isUser = msg.role === 'user'
          const isLastAi = msg.role === 'assistant' && idx === lastAiIndex
          return (
            <div key={msg.message_id} className="chat-row">
              {/* R34(头像布局):头像+昵称行在消息上方(用户右对齐/AI 左对齐) */}
              <div className={`chat-head ${isUser ? 'justify-end' : 'justify-start'}`}>
                {isUser ? userHead : aiHead}
              </div>
              <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                {isUser ? (
                  /* R34:用户气泡纯文本 + @filename 链接(原 renderContent 逻辑),不渲染 markdown */
                  <div className="chat-bubble chat-bubble-user max-w-[85%] px-4 py-3 text-sm whitespace-pre-wrap break-words">
                    {renderContent(msg.content, files)}
                  </div>
                ) : (
                  /* R34:AI 气泡 markdown 全量渲染(md 作用域样式;@filename 链接见容器委托) */
                  <div
                    className="chat-bubble chat-bubble-ai max-w-[92%] px-4 py-3 text-sm md break-words"
                    dangerouslySetInnerHTML={{ __html: aiHtmlMap[msg.message_id] ?? '' }}
                  />
                )}
              </div>
              {/* R34:元信息行(时间戳常显;hover 行内浮现操作栏:复制/重新生成/引用回复) */}
              <div className={`chat-meta ${isUser ? 'justify-end' : 'justify-start'}`}>
                <span>{formatTime(msg.created_at)}</span>
                <span className="chat-meta-acts">
                  <button
                    type="button"
                    className="chat-meta-btn"
                    title={copiedId === msg.message_id ? '已复制' : '复制'}
                    onClick={() => handleCopy(msg.message_id, msg.content)}
                  >
                    {copiedId === msg.message_id
                      ? <Check className="w-3.5 h-3.5" />
                      : <Copy className="w-3.5 h-3.5" />}
                  </button>
                  {isLastAi && (
                    <button
                      type="button"
                      className="chat-meta-btn"
                      title="重新生成"
                      onClick={() => handleRegenerate(idx)}
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <button
                    type="button"
                    className="chat-meta-btn"
                    title="引用回复"
                    onClick={() => handleQuote(msg.content)}
                  >
                    <Quote className="w-3.5 h-3.5" />
                  </button>
                </span>
              </div>
            </div>
          )
        })}
        {/* R34:发送失败的用户消息乐观保留(红描边;meta 行「发送失败 · 点击重试」可点击重发) */}
        {failedUser && (
          <div className="chat-row">
            <div className="chat-head justify-end">{userHead}</div>
            <div className="flex justify-end">
              <div className="chat-bubble chat-bubble-user chat-bubble-error max-w-[85%] px-4 py-3 text-sm whitespace-pre-wrap break-words opacity-80">
                {failedUser}
              </div>
            </div>
            <div className="chat-meta justify-end">
              <button
                type="button"
                className="chat-meta-err"
                onClick={() => {
                  // BUG-UI-089:有发送在途时禁止重试(否则错误态被清而重发被 handleSend
                  // 守卫拦下,该条内容静默丢失)——toast 提示并保留 failedUser
                  if (sendMut.isPending) {
                    showToast('err', '当前有消息发送中,请稍后重试')
                    return
                  }
                  const content = failedUser
                  setFailedUser(null)
                  handleSend(content)
                }}
              >
                发送失败 · 点击重试
              </button>
            </div>
          </div>
        )}
        {/* R32.F9:乐观用户消息(发送即上屏,半透明示「发送中」;刷新后由真消息替换)
            R34(头像布局):同样带当前用户头像行 */}
        {pendingUser && (
          <div>
            <div className="chat-head justify-end">{userHead}</div>
            <div className="flex justify-end">
              <div className="chat-bubble chat-bubble-user max-w-[85%] px-4 py-3 text-sm whitespace-pre-wrap break-words opacity-80">
                {pendingUser}
              </div>
            </div>
          </div>
        )}
        {/* R32.F9:AI 加载动效(头像行 + 三点弹跳;首个增量到达后由流式气泡接管) */}
        {thinking && !streamText && (
          <div>
            <div className="chat-head justify-start">{aiHead}</div>
            <div className="flex justify-start">
              <div className="chat-bubble chat-bubble-ai px-4 py-3">
                <span className="flex items-center gap-1">
                  <span className="chat-dot" />
                  <span className="chat-dot" />
                  <span className="chat-dot" />
                </span>
              </div>
            </div>
          </div>
        )}
        {/* R32.F3:流式增量气泡(AI 正在输出;chat_done/消息落库后消失)
            R34:markdown 渲染 + 呼吸圆点光标 .chat-cursor-dot + AI 头像行 */}
        {streamText && (
          <div>
            <div className="chat-head justify-start">{aiHead}</div>
            <div className="flex justify-start">
              <div className="chat-bubble chat-bubble-ai max-w-[92%] px-4 py-3 text-sm md break-words">
                <div dangerouslySetInnerHTML={{ __html: `${streamHtml}<span class="chat-cursor-dot"></span>` }} />
              </div>
            </div>
          </div>
        )}
        {/* R34.F3:AI 权限确认卡(消息列表尾部)—— 挂起:prompt + 允许/拒绝按钮;
            应答/收口后转「已允许 / 已拒绝 / 已超时拒绝」灰态(opacity-60,按钮移除)。
            复用 AI 气泡容器(.chat-bubble-ai)+ Button 组件 + 既有图标,零新视觉 */}
        {confirmCard && (
          <div>
            <div className="chat-head justify-start">{aiHead}</div>
            <div className="flex justify-start">
              <div
                className={`chat-bubble chat-bubble-ai max-w-[92%] px-4 py-3 text-sm break-words${
                  confirmCard.status === 'pending' ? '' : ' opacity-60'
                }`}
              >
                <div className="whitespace-pre-wrap">{confirmCard.prompt || 'AI 请求执行工具,请确认'}</div>
                {confirmCard.status === 'pending' ? (
                  <div className="flex items-center gap-2 mt-3">
                    <Button type="button" variant="primary" size="sm" onClick={() => handleConfirm('allow')}>
                      <Check className="w-3.5 h-3.5 mr-1" />
                      允许
                    </Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => handleConfirm('deny')}>
                      <X className="w-3.5 h-3.5 mr-1" />
                      拒绝
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1 mt-3 text-xs text-text-secondary">
                    {confirmCard.status === 'allow'
                      ? <Check className="w-3.5 h-3.5 shrink-0" />
                      : <X className="w-3.5 h-3.5 shrink-0" />}
                    {confirmCard.status === 'allow' ? '已允许' : confirmCard.status === 'deny' ? '已拒绝' : '已超时拒绝'}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 附件列表 */}
      {files.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3 py-2 border-t border-border">
          {files.map((f) => (
            <div
              key={f.file_id}
              className="flex items-center gap-1 px-2 py-0.5 text-xs bg-muted rounded"
            >
              <button
                type="button"
                className="hover:text-primary max-w-[140px] truncate"
                onClick={() => handleDownload(f)}
                title={f.filename}
              >
                {f.filename}
              </button>
              <button
                type="button"
                className="text-text-secondary hover:text-danger"
                onClick={() => handleDelete(f.file_id)}
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 发送 pending 反馈(BUG-UI-065:后端同步执行最长 10 分钟,无反馈=像坏了)
          R34:流式期间文案改「AI 正在输出…」并出「■ 停止生成」;
          BUG-UI-086:停止后反馈条改「已停止(服务端仍在执行)」避免误解(点击停止本身触发重渲染,
          ref 读值即新值);
          R34.F1(BUG-UI-090):停止按钮从「有流式增量才出现」放宽为整个 sendMut.isPending 期间
          常显——thinking/后端执行阶段(首个 chat_delta 前,最长 10 分钟)也有停止入口;
          R34.F1:点击已接线后端真取消(messages/cancel),stoppedRef 展示层中止保留为兜底;
          R34.F3:确认挂起期间按钮仍可点(stop 优先,挂起确认由后端按 deny 收口并广播
          resolved{stopped}),反馈条文案给「等待确认」变体引导到列表底部确认卡 */}
      {sendMut.isPending && (
        <div className="px-3 py-1 text-xs text-text-muted flex items-center gap-1.5 border-t border-border">
          <Loader2 className="w-3 h-3 animate-spin" />
          {stoppedRef.current
            ? '已停止(服务端仍在执行)…'
            : confirmCard?.status === 'pending'
              ? '等待确认:请处理消息列表底部的权限确认卡…'
              : streamText
                ? 'AI 正在输出…'
                : 'AI 处理中,请稍候(长任务可能需要数分钟)…'}
          <button type="button" className="chat-stop" onClick={handleStopGeneration}>
            <Square className="w-3 h-3" />
            停止生成
          </button>
        </div>
      )}

      {/* 输入区 */}
      <div className="relative border-t border-border p-2">
        {showAC && (
          <div className="absolute bottom-full left-2 right-2 mb-1 max-h-40 overflow-y-auto bg-popover border border-border rounded-md shadow-md z-10">
            {filteredFiles.length > 0 ? (
              filteredFiles.map((f, i) => (
                <button
                  key={f.file_id}
                  type="button"
                  className={`w-full text-left px-3 py-1.5 text-sm hover:bg-muted ${
                    i === acIndex ? 'bg-muted' : ''
                  }`}
                  ref={i === acIndex ? activeACRef : undefined}
                  onClick={() => selectAC(f.filename)}
                >
                  {f.filename}
                </button>
              ))
            ) : (
              <div className="px-3 py-2 text-sm text-text-secondary text-center">
                {files.length === 0 ? '暂无已上传文件' : '无匹配文件'}
              </div>
            )}
          </div>
        )}
        {/* R32.F2 + R7:/ skill 补全下拉(项目已装 ∪ 系统内置;系统项「内置」徽标,选中插入 /skill名) */}
        {showSC && (
          <div className="absolute bottom-full left-2 right-2 mb-1 max-h-40 overflow-y-auto bg-popover border border-border rounded-md shadow-md z-10">
            {filteredSkills.length > 0 ? (
              filteredSkills.map((s, i) => (
                <button
                  key={`${s.builtin ? 'sys-' : ''}${s.name}`}
                  type="button"
                  className={`w-full text-left px-3 py-1.5 text-sm hover:bg-muted flex items-center gap-2 ${
                    i === scIndex ? 'bg-muted' : ''
                  }`}
                  ref={i === scIndex ? activeSCRef : undefined}
                  onClick={() => selectSC(s.name)}
                >
                  <Sparkles className="w-3.5 h-3.5 text-text-secondary shrink-0" />
                  <span className="font-medium">/{s.name}</span>
                  {s.builtin && <span className="bdg b-zinc bdg-mini shrink-0">内置</span>}
                  {s.description && (
                    <span className="text-text-secondary text-xs truncate">{s.description}</span>
                  )}
                </button>
              ))
            ) : (
              <div className="px-3 py-2 text-sm text-text-secondary text-center">
                {mergedSkills.length === 0 ? '项目未安装 Skill(项目设置 · Skills 中安装)' : '无匹配 Skill'}
              </div>
            )}
          </div>
        )}
        {/* R7:/mcp 补全下拉(项目 MCP 配置 ∪ 系统内置;选中插入 @mcp:名称) */}
        {showMC && (
          <div className="absolute bottom-full left-2 right-2 mb-1 max-h-40 overflow-y-auto bg-popover border border-border rounded-md shadow-md z-10">
            {filteredMcps.length > 0 ? (
              filteredMcps.map((m, i) => (
                <button
                  key={`${m.builtin ? 'sys-' : ''}${m.name}`}
                  type="button"
                  className={`w-full text-left px-3 py-1.5 text-sm hover:bg-muted flex items-center gap-2 ${
                    i === mcIndex ? 'bg-muted' : ''
                  }`}
                  ref={i === mcIndex ? activeMCRef : undefined}
                  onClick={() => selectMC(m.name)}
                >
                  <Plug className="w-3.5 h-3.5 text-text-secondary shrink-0" />
                  <span className="font-medium">@mcp:{m.name}</span>
                  {m.builtin && <span className="bdg b-zinc bdg-mini shrink-0">内置</span>}
                  {m.hint && (
                    <span className="text-text-secondary text-xs truncate">{m.hint}</span>
                  )}
                </button>
              ))
            ) : (
              <div className="px-3 py-2 text-sm text-text-secondary text-center">
                {mcpCandidates.length === 0 ? '暂无 MCP 配置(项目设置 · MCP 配置中添加)' : '无匹配 MCP'}
              </div>
            )}
          </div>
        )}
        <div className="flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            multiple
            onChange={(e) => {
              const list = e.target.files
              if (list) for (let i = 0; i < list.length; i++) handleUpload(list[i])
              e.target.value = ''
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            title="上传文件"
            onClick={() => fileInputRef.current?.click()}
          >
            <Paperclip className="w-4 h-4" />
          </Button>
          {/* R34.F2(BUG-UI-092):模型切换下拉(附件按钮旁;无 projectId / 无启用配置不渲染)。
              按钮显示当前配置 name,展开列出各配置(name + model 小字 + 默认徽标,选中项打勾);
              config_id 后端消费待契约(占位) */}
          {projectId && currentModelConfig && (
            <div className="relative shrink-0">
              <Button
                type="button"
                variant="outline"
                size="sm"
                title="切换模型"
                onClick={() => setShowModelDD((v) => !v)}
              >
                <span className="max-w-[110px] truncate">{currentModelConfig.name}</span>
                <ChevronDown className="w-3.5 h-3.5 ml-0.5 shrink-0" />
              </Button>
              {showModelDD && (
                <div className="absolute bottom-full left-0 mb-1 w-56 max-h-60 overflow-y-auto bg-popover border border-border rounded-md shadow-md z-10">
                  {modelConfigs.map((c) => (
                    <button
                      key={c.config_id}
                      type="button"
                      className={`w-full text-left px-3 py-1.5 text-sm hover:bg-muted flex items-start gap-2 ${
                        c.config_id === currentModelConfig.config_id ? 'bg-muted' : ''
                      }`}
                      onClick={() => {
                        setSelectedConfigId(c.config_id)
                        setShowModelDD(false)
                      }}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium truncate">{c.name}</span>
                          {c.is_default && <span className="bdg b-zinc bdg-mini shrink-0">默认</span>}
                        </div>
                        <div className="text-xs text-text-secondary truncate">{c.model}</div>
                      </div>
                      {c.config_id === currentModelConfig.config_id && (
                        <Check className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          <input
            type="text"
            value={input}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={(e) => {
              // R34(补全键盘导航):下拉展开且有候选时,方向键循环移动高亮、Enter 选中高亮项
              //(不发送;Escape 关闭已有)。无候选下落回原发送行为
              if (showAC && filteredFiles.length > 0) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  setAcIndex((i) => (i + 1) % filteredFiles.length)
                  return
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  setAcIndex((i) => (i - 1 + filteredFiles.length) % filteredFiles.length)
                  return
                }
                if (e.key === 'Enter') {
                  e.preventDefault()
                  const hit = filteredFiles[acIndex]
                  if (hit) selectAC(hit.filename)
                  return
                }
              } else if (showSC && filteredSkills.length > 0) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  setScIndex((i) => (i + 1) % filteredSkills.length)
                  return
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  setScIndex((i) => (i - 1 + filteredSkills.length) % filteredSkills.length)
                  return
                }
                if (e.key === 'Enter') {
                  e.preventDefault()
                  const hit = filteredSkills[scIndex]
                  if (hit) selectSC(hit.name)
                  return
                }
              } else if (showMC && filteredMcps.length > 0) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  setMcIndex((i) => (i + 1) % filteredMcps.length)
                  return
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  setMcIndex((i) => (i - 1 + filteredMcps.length) % filteredMcps.length)
                  return
                }
                if (e.key === 'Enter') {
                  e.preventDefault()
                  const hit = filteredMcps[mcIndex]
                  if (hit) selectMC(hit.name)
                  return
                }
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
              if (e.key === 'Escape') { setShowAC(false); setShowSC(false); setShowMC(false); setShowModelDD(false) }
            }}
            ref={inputRef}
            placeholder={projectId ? '输入消息,@ 引用文件,/ 调用 Skill,/mcp 引用 MCP...' : '输入消息,@ 引用已上传文件...'}
            className="flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <Button type="button" size="sm" onClick={() => handleSend()} disabled={!input.trim() || sendMut.isPending}>
            {sendMut.isPending ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Send className="w-4 h-4 mr-1" />}
            {sendMut.isPending ? '发送中' : '发送'}
          </Button>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className={`absolute bottom-16 left-1/2 -translate-x-1/2 px-3 py-1.5 text-sm rounded shadow-md ${
            toast.type === 'ok' ? 'bg-success text-white' : 'bg-danger text-white'
          }`}
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}
