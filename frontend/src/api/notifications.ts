/**
 * Notifications API — 站内信列表 / 未读数 / 已读标记 / 通知设置
 * 后端契约: backend/app/api/notifications.py
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

/* ── 类型定义 ── */

/** 通知级别 */
export type NotificationLevel = 'critical' | 'normal' | 'info'

/** 通知类型枚举 */
export type NotificationType =
  | 'deploy_failed'
  | 'runner_offline'
  | 'task_failed'
  | 'push_failed'
  | 'review_approved'
  | 'review_rejected'
  | 'invited_to_project'
  | 'task_done'
  | 'deployed'

/** 单条通知 */
export interface NotificationItem {
  notification_id: string
  type: NotificationType
  level: NotificationLevel
  title: string
  content: string
  link: string | null
  project_id: string | null
  task_id: string | null
  read_at: string | null
  created_at: string
}

/** 列表响应 */
export interface NotificationListData {
  items: NotificationItem[]
  total: number
  unread_count: number
  page: number
  page_size: number
}

/** 列表查询参数 */
export interface NotificationListParams {
  type?: NotificationType
  level?: NotificationLevel
  read?: 'true' | 'false'
  page?: number
  page_size?: number
}

/** 未读数 */
export interface UnreadCountData {
  unread_count: number
}

/** 个人通知设置 */
export interface NotificationSettings {
  dingtalk_webhook: string | null
  dingtalk_enabled: boolean
  realtime_toast_enabled: boolean
}

/** 更新通知设置请求 */
export interface UpdateNotificationSettingsRequest {
  dingtalk_webhook?: string
  dingtalk_enabled?: boolean
  realtime_toast_enabled?: boolean
}

/* ── 通知类型中文映射 ── */

export const NOTIFICATION_TYPE_CN: Record<NotificationType, string> = {
  deploy_failed: '部署失败',
  runner_offline: 'Runner 离线',
  task_failed: '任务失败',
  push_failed: '推送失败',
  review_approved: '评审通过',
  review_rejected: '评审驳回',
  invited_to_project: '项目邀请',
  task_done: '任务完成',
  deployed: '部署成功',
}

export const NOTIFICATION_LEVEL_CN: Record<NotificationLevel, string> = {
  critical: '严重',
  normal: '普通',
  info: '信息',
}

/* ── API 调用 ── */

export const notificationsApi = {
  /** 通知列表(分页 + 筛选) */
  list: (params?: NotificationListParams) => {
    const qs = new URLSearchParams()
    if (params?.type) qs.set('type', params.type)
    if (params?.level) qs.set('level', params.level)
    if (params?.read) qs.set('read', params.read)
    if (params?.page) qs.set('page', String(params.page))
    if (params?.page_size) qs.set('page_size', String(params.page_size))
    const q = qs.toString()
    return api.get<NotificationListData>(`/notifications${q ? `?${q}` : ''}`)
  },

  /** 未读数 */
  unreadCount: () => api.get<UnreadCountData>('/notifications/unread-count'),

  /** 标记单条已读 */
  markRead: (notificationId: string) =>
    api.post<{ message: string }>(`/notifications/${notificationId}/read`),

  /** 全部标记已读 */
  markAllRead: () =>
    api.post<{ message: string }>('/notifications/read-all'),

  /** 删除通知 */
  remove: (notificationId: string) =>
    api.delete<{ message: string }>(`/notifications/${notificationId}`),

  /** 获取个人通知设置 */
  getSettings: () =>
    api.get<NotificationSettings>('/users/me/notification-settings'),

  /** 更新个人通知设置 */
  updateSettings: (data: UpdateNotificationSettingsRequest) =>
    api.put<{ message: string }>('/users/me/notification-settings', data),

  /** 测试钉钉 webhook */
  testDingtalk: (data?: UpdateNotificationSettingsRequest) =>
    api.post<{ message: string }>('/users/me/notification-settings/test-dingtalk', data),
}

/* ── React Query Hooks ── */

/** 通知列表 */
export function useNotificationList(params?: NotificationListParams) {
  return useQuery({
    queryKey: ['notifications', params],
    queryFn: () => notificationsApi.list(params).then((r) => r.data),
  })
}

/** 未读数 */
export function useUnreadCount() {
  return useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => notificationsApi.unreadCount().then((r) => r.data),
    refetchInterval: 60_000, // 60s 轮询
  })
}

/** 个人通知设置 */
export function useNotificationSettings() {
  return useQuery({
    queryKey: ['notification-settings'],
    queryFn: () => notificationsApi.getSettings().then((r) => r.data),
  })
}

/** 标记单条已读 */
export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notificationId: string) =>
      notificationsApi.markRead(notificationId).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

/** 全部标记已读 */
export function useMarkAllRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => notificationsApi.markAllRead().then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

/** 删除通知 */
export function useDeleteNotification() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notificationId: string) =>
      notificationsApi.remove(notificationId).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

/** 更新通知设置 */
export function useUpdateNotificationSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UpdateNotificationSettingsRequest) =>
      notificationsApi.updateSettings(data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notification-settings'] })
    },
  })
}

/** 测试钉钉 webhook */
export function useTestDingtalk() {
  return useMutation({
    mutationFn: (data?: UpdateNotificationSettingsRequest) =>
      notificationsApi.testDingtalk(data).then((r) => r.data),
  })
}
