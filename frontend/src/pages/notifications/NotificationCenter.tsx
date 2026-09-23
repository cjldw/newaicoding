/**
 * 通知中心页 /notifications
 * - 分类 Tab(全部 / 严重 / 普通 / 信息)+ 全部已读按钮
 * - 列表:类型徽章 / 标题 / 时间 / 已读态;点击跳转 link 或标记已读
 * - 分页(后端 page/page_size)
 * - 空态 .empty
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell, CheckCheck, ChevronLeft, ChevronRight, Trash2, ExternalLink, Loader2,
} from 'lucide-react'
import {
  useNotificationList, useMarkAllRead, useMarkNotificationRead, useDeleteNotification,
  NOTIFICATION_TYPE_CN, NOTIFICATION_LEVEL_CN,
  type NotificationLevel, type NotificationItem,
} from '@/api/notifications'
import { useToast } from '@/hooks/useToast'

/** Tab 定义 */
const TABS: { key: NotificationLevel | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'critical', label: '严重' },
  { key: 'normal', label: '普通' },
  { key: 'info', label: '信息' },
]

/** 级别 → 徽章颜色类 */
function levelBadgeCls(level: NotificationLevel): string {
  switch (level) {
    case 'critical': return 'bdg b-red'
    case 'normal': return 'bdg b-blue'
    case 'info': return 'bdg b-zinc'
  }
}

/** 相对时间 */
function timeAgo(dateStr: string): string {
  const d = new Date(dateStr)
  const now = Date.now()
  const diff = now - d.getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} 天前`
  return d.toLocaleDateString('zh-CN')
}

const PAGE_SIZE = 20

export function NotificationCenter() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<NotificationLevel | 'all'>('all')
  const [page, setPage] = useState(1)
  const [, showToast, ToastEl] = useToast()

  const params = useMemo(() => ({
    level: tab === 'all' ? undefined : tab,
    page,
    page_size: PAGE_SIZE,
  }), [tab, page])

  const { data, isLoading, isFetching } = useNotificationList(params)
  const markRead = useMarkNotificationRead()
  const markAllRead = useMarkAllRead()
  const deleteNotif = useDeleteNotification()

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  async function handleMarkAllRead() {
    try {
      await markAllRead.mutateAsync()
      showToast('ok', '已全部标记为已读')
    } catch {
      showToast('err', '操作失败')
    }
  }

  async function handleItemClick(item: NotificationItem) {
    // 未读 → 标记已读
    if (!item.read_at) {
      try { await markRead.mutateAsync(item.notification_id) } catch { /* 静默 */ }
    }
    // 有 link → 跳转
    if (item.link) {
      navigate(item.link)
      return
    }
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    try {
      await deleteNotif.mutateAsync(id)
      showToast('ok', '已删除')
    } catch {
      showToast('err', '删除失败')
    }
  }

  function handleTabChange(key: NotificationLevel | 'all') {
    setTab(key)
    setPage(1) // 切 tab 重置分页
  }

  return (
    <div className="page">
      <div className="page-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Bell size={20} />
          <h1 style={{ fontSize: 18, fontWeight: 600 }}>通知中心</h1>
          {data?.unread_count ? (
            <span className="bdg b-red">{data.unread_count} 未读</span>
          ) : null}
          {isFetching && <Loader2 size={14} className="animate-spin" style={{ opacity: 0.5 }} />}
        </div>
        <div className="acts">
          <button
            className="btn btn-sm"
            onClick={handleMarkAllRead}
            disabled={markAllRead.isPending || !items.length}
          >
            <CheckCheck size={13} style={{ marginRight: 4 }} />
            全部已读
          </button>
        </div>
      </div>

      {/* Tab 栏 */}
      <div className="tabs" style={{ marginBottom: 0 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab${tab === t.key ? ' on' : ''}`}
            onClick={() => handleTabChange(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 列表 */}
      <div className="card" style={{ borderRadius: '0 0 var(--vp-radius) var(--vp-radius)', borderTop: 'none' }}>
        <div className="card-body tight">
          {isLoading ? (
            <div className="empty" style={{ padding: '60px 0' }}>
              <Loader2 size={20} className="animate-spin" style={{ margin: '0 auto 8px' }} />
              <div>加载中…</div>
            </div>
          ) : items.length === 0 ? (
            <div className="empty" style={{ padding: '60px 0' }}>
              <Bell size={24} style={{ margin: '0 auto 8px', opacity: 0.3 }} />
              <div>暂无通知</div>
            </div>
          ) : (
            <table className="tbl" style={{ marginBottom: 0 }}>
              <thead>
                <tr>
                  <th style={{ width: 80 }}>级别</th>
                  <th>标题</th>
                  <th style={{ width: 90 }}>类型</th>
                  <th style={{ width: 100 }}>时间</th>
                  <th style={{ width: 50 }}></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.notification_id}
                    className="rowclick"
                    onClick={() => handleItemClick(item)}
                    style={{
                      opacity: item.read_at ? 0.6 : 1,
                      cursor: item.link ? 'pointer' : 'default',
                    }}
                  >
                    <td>
                      <span className={levelBadgeCls(item.level)}>
                        {NOTIFICATION_LEVEL_CN[item.level]}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {!item.read_at && (
                          <span className="dot pulse" style={{ background: 'var(--primary)', flexShrink: 0 }} />
                        )}
                        <span style={{
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          fontWeight: item.read_at ? 400 : 500,
                        }}>
                          {item.title}
                        </span>
                        {item.link && <ExternalLink size={12} style={{ opacity: 0.3, flexShrink: 0 }} />}
                      </div>
                      {item.content && (
                        <div className="small muted" style={{
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          marginTop: 2,
                        }}>
                          {item.content}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="small">{NOTIFICATION_TYPE_CN[item.type] ?? item.type}</span>
                    </td>
                    <td>
                      <span className="small muted">{timeAgo(item.created_at)}</span>
                    </td>
                    <td>
                      <button
                        className="btn btn-ghost icon-btn"
                        title="删除"
                        onClick={(e) => handleDelete(e, item.notification_id)}
                        style={{ width: 24, height: 24 }}
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* 分页 */}
        {totalPages > 1 && (
          <div className="card-foot" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>共 {total} 条</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                className="btn btn-sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft size={13} />
              </button>
              <span className="small">{page} / {totalPages}</span>
              <button
                className="btn btn-sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                <ChevronRight size={13} />
              </button>
            </div>
          </div>
        )}
      </div>

      {ToastEl}
    </div>
  )
}
