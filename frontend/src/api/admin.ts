/**
 * Admin API — 用户管理/邀请/审计日志(仅超管,R19)
 * - 用户列表:GET /api/admin/users(status/q/page/page_size)
 * - 禁用启用:PATCH /api/admin/users/{user_id}/status
 * - 邀请:POST /api/admin/invitations, GET /api/admin/invitations, DELETE /api/admin/invitations/{id}
 * - 审计:GET /api/admin/audit-logs(start_time/end_time/user_id/action_type/project_id/page/page_size)
 */

import { api } from './client'

// ========== 平台设置 ==========

export interface PlatformSettings {
  // GitLab 集成
  gitlab_url: string | null
  gitlab_bot_token: string | null  // 打码格式
  gitlab_bot_group_id: number | string | null
  gitlab_webhook_secret: string | null  // 打码格式
  // 域名配置
  preview_base_domain: string | null
  deploy_base_domain: string | null
  // 全局参数
  max_containers_total: number | null
  kb_max_pages_per_kb: number | null
  kb_max_file_mb: number | null
  // 模型默认配置(R23)
  llm_base_url: string | null
  llm_api_key: string | null  // 打码格式
  llm_model: string | null
  // 自定义容器环境变量(R8.F4;原样回显不打码)
  custom_env_vars: Record<string, string> | null
}

// ========== 用户管理 ==========

export interface AdminUser {
  user_id: string
  phone: string // 打码:138****5678
  nickname: string | null
  avatar_url: string | null
  role: string // 'superadmin' | 'user'
  status: string // 'active' | 'disabled'
  gitlab_bound: boolean
  created_at: string
}

export interface AdminUsersResponse {
  items: AdminUser[]
  total: number
}

export interface AdminUsersParams {
  status?: string
  q?: string
  page?: number
  page_size?: number
}

export const adminUsersApi = {
  list: (params: AdminUsersParams = {}) => {
    const qs = new URLSearchParams()
    if (params.status) qs.set('status', params.status)
    if (params.q) qs.set('q', params.q)
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    const query = qs.toString()
    return api.get<AdminUsersResponse>(`/admin/users${query ? `?${query}` : ''}`)
  },

  updateStatus: (userId: string, status: 'active' | 'disabled') =>
    api.patch<{ user_id: string; status: string; cancelled_tasks: number }>(
      `/admin/users/${userId}/status`,
      { status },
    ),
}

// ========== 邀请管理 ==========

export interface Invitation {
  invitation_id: string
  invited_phone: string // 打码
  status: string // 'pending' | 'used' | 'expired' | 'revoked'
  created_by: string
  created_at: string
  expires_at: string
}

export interface InvitationsResponse {
  items: Invitation[]
  total: number
}

export interface InvitationCreateResponse {
  invitation_id: string
  invitation_token: string
  expires_at: string
}

export const adminInvitationsApi = {
  list: () => api.get<InvitationsResponse>('/admin/invitations'),

  create: (invited_phone: string) =>
    api.post<InvitationCreateResponse>('/admin/invitations', { invited_phone }),

  revoke: (invitationId: string) =>
    api.delete<{ invitation_id: string }>(`/admin/invitations/${invitationId}`),
}

// ========== 审计日志 ==========

export interface AuditLog {
  log_id: string
  user_id: string
  operator_nickname: string | null
  operator_role: string
  action_type: string
  project_id: string | null
  target_type: string | null
  target_id: string | null
  detail: Record<string, unknown> | null
  ip: string | null
  created_at: string
}

export interface AuditLogsResponse {
  items: AuditLog[]
  total: number
}

export interface AuditLogsParams {
  start_time?: string
  end_time?: string
  user_id?: string
  action_type?: string
  project_id?: string
  page?: number
  page_size?: number
}

export const adminAuditLogsApi = {
  list: (params: AuditLogsParams = {}) => {
    const qs = new URLSearchParams()
    if (params.start_time) qs.set('start_time', params.start_time)
    if (params.end_time) qs.set('end_time', params.end_time)
    if (params.user_id) qs.set('user_id', params.user_id)
    if (params.action_type) qs.set('action_type', params.action_type)
    if (params.project_id) qs.set('project_id', params.project_id)
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    const query = qs.toString()
    return api.get<AuditLogsResponse>(`/admin/audit-logs${query ? `?${query}` : ''}`)
  },
}
