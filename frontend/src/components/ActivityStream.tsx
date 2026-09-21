/**
 * ActivityStream — 任务实时事件流
 * WebSocket /ws/tasks/{taskId}/events?token=...
 * 渲染 tool_call(name + duration) 和 status_changed 事件
 * 最多 200 条,自动滚动到底部
 */

import { useEffect, useRef, useState } from 'react'
import { useAuthStore } from '@/stores/authStore'

interface ActivityStreamProps {
  taskId: string
}

export type ActivityEvent =
  | {
      event_id: string
      type: 'tool_call'
      tool_name: string
      duration_ms: number
      status: 'running' | 'done' | 'error'
      created_at: string
    }
  | {
      event_id: string
      type: 'status_changed'
      from_status: string
      to_status: string
      created_at: string
    }
  | {
      event_id: string
      type: 'log'
      level: 'info' | 'warn' | 'error'
      message: string
      created_at: string
    }

const MAX_EVENTS = 200

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTime(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

export function ActivityStream({ taskId }: ActivityStreamProps) {
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // 自动滚动到底部
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [events.length])

  // WebSocket 连接
  useEffect(() => {
    const token = useAuthStore.getState().token
    if (!token || !taskId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/tasks/${taskId}/events?token=${token}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as ActivityEvent
        setEvents((prev) => {
          const next = [...prev, event]
          // 最多保留 200 条
          return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
        })
      } catch {
        // 忽略非法消息
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [taskId])

  return (
    <div className="flex flex-col w-full h-full min-h-0 border border-border rounded-md bg-background">
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-sm font-medium text-foreground">活动流</span>
        <span
          className={`inline-block w-2 h-2 rounded-full ${
            connected ? 'bg-success' : 'bg-text-secondary'
          }`}
          title={connected ? '已连接' : '未连接'}
        />
      </div>

      {/* 事件列表 */}
      <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto p-3 space-y-1.5">
        {events.length === 0 && (
          <div className="text-center text-text-secondary text-sm py-8">
            {connected ? '等待活动...' : '未连接'}
          </div>
        )}
        {events.map((ev) => (
          <div key={ev.event_id} className="flex items-start gap-2 text-xs">
            <span className="text-text-secondary shrink-0 w-16">
              {formatTime(ev.created_at)}
            </span>
            {ev.type === 'tool_call' && (
              <div className="flex items-center gap-1.5 flex-1 min-w-0">
                <span
                  className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                    ev.status === 'running'
                      ? 'bg-primary animate-pulse'
                      : ev.status === 'done'
                        ? 'bg-success'
                        : 'bg-danger'
                  }`}
                />
                <span className="text-foreground truncate">
                  {ev.tool_name}
                </span>
                <span className="text-text-secondary shrink-0">
                  {formatDuration(ev.duration_ms)}
                </span>
              </div>
            )}
            {ev.type === 'status_changed' && (
              <div className="flex items-center gap-1 flex-1 min-w-0">
                <span className="text-text-secondary">{ev.from_status}</span>
                <span className="text-text-secondary">→</span>
                <span className="text-primary font-medium">{ev.to_status}</span>
              </div>
            )}
            {ev.type === 'log' && (
              <div className="flex-1 min-w-0">
                <span
                  className={
                    ev.level === 'error'
                      ? 'text-danger'
                      : ev.level === 'warn'
                        ? 'text-warning'
                        : 'text-foreground'
                  }
                >
                  {ev.message}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
