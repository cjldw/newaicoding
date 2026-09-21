/**
 * Requirements API — 需求 CRUD + 打磨/评审/取消 + react-query hooks
 * 错误码: 3001 已有打磨任务进行中, 3002 需求状态不是 polishing
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from './client'

// ---- Types ----
export interface RequirementUser {
  user_id: string
  username: string
  nickname: string
}

export interface RequirementListItem {
  req_id: string
  title: string
  status: RequirementStatus
  priority: RequirementPriority
  created_by: RequirementUser
  created_at: string
}

export type RequirementStatus =
  | 'draft' | 'polishing' | 'reviewing' | 'approved'
  | 'in_progress' | 'done' | 'archived' | 'rejected'

export type RequirementPriority = 'low' | 'medium' | 'high'

export interface RequirementListResponse {
  items: RequirementListItem[]
  total: number
  page: number
  page_size: number
}

export interface RequirementTask {
  task_id: string
  type: 'requirement' | 'dev' | 'test' | 'release'
  title: string
  status: string
}

export interface RequirementDetail {
  req_id: string
  title: string
  background: string
  description: string
  acceptance_criteria: string
  status: RequirementStatus
  priority: RequirementPriority
  req_branch: string
  prd_file_path: string
  created_by: RequirementUser
  reviewed_by: RequirementUser | null
  reviewed_at: string | null
  reject_reason: string | null
  polish_task_id: string | null
  tasks: RequirementTask[]
  created_at: string
  updated_at: string
}

export interface CreateRequirementRequest {
  title: string
  background?: string
  description: string
  acceptance_criteria?: string
  priority?: RequirementPriority
  req_branch?: string
}

export interface CreateRequirementResponse {
  req_id: string
  req_branch: string
}

export interface UpdateRequirementRequest {
  title?: string
  background?: string
  description?: string
  acceptance_criteria?: string
  priority?: RequirementPriority
}

export interface ReviewRequest {
  approved: boolean
  reject_reason?: string
}

export interface CancelRequest {
  reason: string
}

// ---- API calls ----
export const requirementsApi = {
  list: (projectId: string, params: { status?: string; page?: number; page_size?: number }) => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.page) query.set('page', String(params.page))
    if (params.page_size) query.set('page_size', String(params.page_size))
    return api.get<RequirementListResponse>(`/projects/${projectId}/requirements?${query.toString()}`)
  },
  detail: (reqId: string) => api.get<RequirementDetail>(`/requirements/${reqId}`),
  create: (projectId: string, data: CreateRequirementRequest) =>
    api.post<CreateRequirementResponse>(`/projects/${projectId}/requirements`, data),
  update: (reqId: string, data: UpdateRequirementRequest) =>
    api.patch<RequirementDetail>(`/requirements/${reqId}`, data),
  polish: (reqId: string) =>
    api.post<{ task_id: string }>(`/requirements/${reqId}/polish`),
  submitReview: (reqId: string) =>
    api.post<{ message: string }>(`/requirements/${reqId}/submit-review`),
  review: (reqId: string, data: ReviewRequest) =>
    api.post<{ message: string }>(`/requirements/${reqId}/review`, data),
  cancel: (reqId: string, data: CancelRequest) =>
    api.post<{ message: string }>(`/requirements/${reqId}/cancel`, data),
}

// ---- Error code helpers ----
export function getRequirementErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 3001: return '已有打磨任务进行中'
      case 3002: return '需求状态不是打磨中'
      default: return error.message
    }
  }
  return '操作失败'
}

// ---- React Query Hooks ----
export function useRequirementList(
  projectId: string,
  params: { status?: string; page?: number; page_size?: number },
) {
  return useQuery({
    queryKey: ['requirements', projectId, params],
    queryFn: () => requirementsApi.list(projectId, params).then(r => r.data),
    enabled: !!projectId,
  })
}

export function useRequirementDetail(reqId: string) {
  return useQuery({
    queryKey: ['requirement', reqId],
    queryFn: () => requirementsApi.detail(reqId).then(r => r.data),
    enabled: !!reqId,
  })
}

export function useCreateRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: { projectId: string; data: CreateRequirementRequest }) =>
      requirementsApi.create(projectId, data).then(r => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['requirements', variables.projectId] })
    },
  })
}

export function useUpdateRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ reqId, data }: { reqId: string; data: UpdateRequirementRequest }) =>
      requirementsApi.update(reqId, data).then(r => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['requirement', variables.reqId] })
    },
  })
}

export function usePolishRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (reqId: string) => requirementsApi.polish(reqId).then(r => r.data),
    onSuccess: (_data, reqId) => {
      qc.invalidateQueries({ queryKey: ['requirement', reqId] })
    },
  })
}

export function useSubmitReview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (reqId: string) => requirementsApi.submitReview(reqId),
    onSuccess: (_data, reqId) => {
      qc.invalidateQueries({ queryKey: ['requirement', reqId] })
    },
  })
}

export function useReviewRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ reqId, data }: { reqId: string; data: ReviewRequest }) =>
      requirementsApi.review(reqId, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['requirement', variables.reqId] })
    },
  })
}

export function useCancelRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ reqId, data }: { reqId: string; data: CancelRequest }) =>
      requirementsApi.cancel(reqId, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['requirement', variables.reqId] })
    },
  })
}
