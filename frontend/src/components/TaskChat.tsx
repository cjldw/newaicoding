/**
 * TaskChat — 任务对话框
 * - 消息列表(user 右侧/assistant 左侧气泡,@filename 渲染为链接)
 * - 输入框(@ 触发已上传文件自动补全下拉)
 * - 附件按钮(Paperclip,提示"上传文件")+ 拖拽上传
 * - 附件列表(文件名点击下载,X 删除)
 * - 发送按钮"发送"
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Maximize2, Minimize2, Paperclip, Send, X } from 'lucide-react'
import { Button } from './ui/Button'
import {
  useTaskMessages, useSendTaskMessage, useUploadTaskFile,
  useUploadedFiles, useDeleteTaskFile, downloadTaskFile,
  getTaskErrorMessage,
} from '@/api/tasks'
import type { TaskMessage, UploadedFile } from '@/api/tasks'
import { ApiError } from '@/api/client'

interface TaskChatProps {
  taskId: string
  /** 全屏(BUG-UI-064:CSS 提升为 fixed 覆盖层,组件不重挂载,消息与输入态保留) */
  fullscreen?: boolean
  onToggleFullscreen?: () => void
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

export function TaskChat({ taskId, fullscreen = false, onToggleFullscreen }: TaskChatProps) {
  const { data: msgData } = useTaskMessages(taskId)
  const { data: uploadsData, refetch: refetchUploads } = useUploadedFiles(taskId)
  const sendMut = useSendTaskMessage(taskId)
  const uploadMut = useUploadTaskFile(taskId)
  const deleteMut = useDeleteTaskFile(taskId)

  const [input, setInput] = useState('')
  const [showAC, setShowAC] = useState(false)
  const [acIndex, setAcIndex] = useState(0)
  const [toast, setToast] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const messages: TaskMessage[] = msgData?.items ?? []
  const files: UploadedFile[] = uploadsData?.items ?? []

  // 自动滚动到底部
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages.length])

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

  // @ 自动补全
  const handleInputChange = (v: string) => {
    setInput(v)
    const atMatch = v.match(/@(\S*)$/)
    if (atMatch) {
      setShowAC(true)
      setAcIndex(0)
    } else {
      setShowAC(false)
    }
  }

  const selectAC = (filename: string) => {
    const replaced = input.replace(/@\S*$/, `@${filename} `)
    setInput(replaced)
    setShowAC(false)
  }

  const filteredFiles = files.filter((f) => {
    const atMatch = input.match(/@(\S*)$/)
    if (!atMatch) return false
    return f.filename.toLowerCase().includes(atMatch[1].toLowerCase())
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
                className={`max-w-[80%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap break-words ${
                  isUser
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground'
                }`}
              >
                {isUser ? msg.content : renderContent(msg.content, files)}
              </div>
            </div>
          )
        })}
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
            }}
            placeholder="输入消息,@ 引用已上传文件..."
            className="flex-1 px-3 py-1.5 text-sm bg-background border border-border rounded focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <Button type="button" size="sm" onClick={handleSend} disabled={!input.trim()}>
            <Send className="w-4 h-4 mr-1" />
            发送
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
