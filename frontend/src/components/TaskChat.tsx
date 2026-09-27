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
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Loader2, Maximize2, Minimize2, Paperclip, Plug, Send, Sparkles, X } from 'lucide-react'
import { Button } from './ui/Button'
import {
  useTaskMessages, useSendTaskMessage, useUploadTaskFile,
  useUploadedFiles, useDeleteTaskFile, downloadTaskFile,
  getTaskErrorMessage, useTaskChatStream,
} from '@/api/tasks'
import type { TaskMessage, UploadedFile } from '@/api/tasks'
import { mcpApi, skillsApi, systemAssetsApi, type McpConfig, type Skill, type SystemAssetsData } from '@/api/skills'
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
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const messages: TaskMessage[] = msgData?.items ?? []
  const files: UploadedFile[] = uploadsData?.items ?? []

  // R32.F2:项目已装 Skills(仅 projectId 就绪时拉一次)
  useEffect(() => {
    if (!projectId) return
    skillsApi.installed(projectId)
      .then((d) => setSkills(d.data?.items ?? []))
      .catch(() => setSkills([]))
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
  useTaskChatStream(taskId, {
    onDelta: (text) => setStreamText((prev) => prev + text),
    onDone: () => setStreamText(''),
  })

  // 自动滚动到底部(新消息或流式增量都触发)
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages.length, streamText])

  // toast 自动消失
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 2500)
    return () => clearTimeout(t)
  }, [toast])

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

  // R32.F2:选中 skill → 输入框插入 @skill名(claude CLI 原生 skill 引用格式)
  const selectSC = (skillName: string) => {
    const replaced = input.replace(/\/(\S*)$/, `@${skillName} `)
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

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed) return
    sendMut.mutate(trimmed, {
      onSuccess: () => setInput(''),
      onError: (err) => {
        const code = err instanceof ApiError ? err.code : 0
        showToast('err', getTaskErrorMessage(code, '发送失败'))
      },
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

      {/* 消息列表 */}
      <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-text-secondary text-sm py-8">
            暂无消息,发送第一条指令开始任务
          </div>
        )}
        {messages.map((msg) => {
          const isUser = msg.role === 'user'
          return (
            <div
              key={msg.message_id}
              className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`chat-bubble max-w-[80%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap break-words ${
                  isUser ? 'chat-bubble-user' : 'chat-bubble-ai'
                }`}
              >
                {isUser ? msg.content : renderContent(msg.content, files)}
              </div>
            </div>
          )
        })}
        {/* R32.F3:流式增量气泡(AI 正在输出;chat_done/消息落库后消失) */}
        {streamText && (
          <div className="flex justify-start">
            <div className="chat-bubble chat-bubble-ai max-w-[80%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap break-words">
              {streamText}
              <span className="inline-block w-1.5 h-3.5 ml-0.5 align-text-bottom bg-foreground/60 animate-pulse" />
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

      {/* 发送 pending 反馈(BUG-UI-065:后端同步执行最长 10 分钟,无反馈=像坏了) */}
      {sendMut.isPending && (
        <div className="px-3 py-1 text-xs text-text-muted flex items-center gap-1.5 border-t border-border">
          <Loader2 className="w-3 h-3 animate-spin" />
          AI 处理中,请稍候(长任务可能需要数分钟)…
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
        {/* R32.F2 + R7:/ skill 补全下拉(项目已装 ∪ 系统内置;系统项「内置」徽标,选中插入 @skill名) */}
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
          <input
            type="text"
            value={input}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
              if (e.key === 'Escape') { setShowAC(false); setShowSC(false); setShowMC(false) }
            }}
            placeholder={projectId ? '输入消息,@ 引用文件,/ 调用 Skill,/mcp 引用 MCP...' : '输入消息,@ 引用已上传文件...'}
            className="flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <Button type="button" size="sm" onClick={handleSend} disabled={!input.trim() || sendMut.isPending}>
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
