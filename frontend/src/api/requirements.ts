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
  // R5 交付时间(DATE 纯日期串 YYYY-MM-DD;存量行 NULL,前端列表逾期徽章判定用)
  delivery_date?: string | null
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

// R4 原型链接:label 可空(≤20,后端截断;空则前端展示「链接 N」),url 需 http(s):// 开头;最多 10 条(超限/非法整组 400)
export interface RequirementPrototypeLink {
  label: string | null
  url: string
}

export interface RequirementDetail {
  req_id: string
  // R2:归属项目 id(详情页据此拉项目成员:chips 昵称/头像解析 + 编辑权限判定 + 编辑候选)。
  // 可选:后端未透出时 undefined,前端降级(chips 无成员信息、隐藏编辑入口),不炸
  project_id?: string
  title: string
  background: string
  description: string
  acceptance_criteria: string
  status: RequirementStatus
  priority: RequirementPriority
  req_branch: string
  prd_file_path: string
  // R1 关联用户(后端契约:RequirementDetailData.related_user_ids,存量行 NULL=空)
  related_user_ids?: string[]
  // R4 原型链接(存量行 NULL=空;空列表详情不渲染该行)
  prototype_links?: RequirementPrototypeLink[]
  // R5 交付时间(DATE 纯日期串;存量行 NULL=空,详情有值才渲染该行)
  delivery_date?: string | null
  created_by: RequirementUser
  reviewed_by: RequirementUser | null
  reviewed_at: string | null
  reject_reason: string | null
  polish_task_id: string | null
  /** R35.F1:打磨任务状态透传(「重新打磨」按钮可见性,免二次请求) */
  polish_task_status: string | null
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
  // R5 交付时间:非必填(date picker 到天,YYYY-MM-DD;不填=不设置)
  delivery_date?: string | null
  // R1 关联用户:项目成员 user_id 列表,非必填,空数组照传(后端静默剔除非成员+去重)
  related_user_ids?: string[]
  // R4 原型链接:非必填;≤10 条、url http(s):// 开头、label 截断 20(后端非法整组 400)
  prototype_links?: RequirementPrototypeLink[]
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
  // R2 关联用户:传了(含 [])即全量覆盖(后端剔除非成员+去重;[] = 清空合法);不传(None)= 不动现有名单
  related_user_ids?: string[]
  // R5 交付时间:与创建同形(date|None,可清空;PATCH 唯一「不传即置空」字段,提交须回填当前值)
  delivery_date?: string | null
  // R4 原型链接:与创建同校验(≤10 条、url http(s):// 开头;编辑维护走 PATCH)
  prototype_links?: RequirementPrototypeLink[]
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
  // R1.F2:分支名预览(后端拼音策略权威生成;title 必填 1-128,与创建时 default_req_branch 同口径)
  branchPreview: (title: string) =>
    api.get<{ branch: string }>(`/requirements/branch-preview?title=${encodeURIComponent(title)}`),
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

// R1.F2:分支名预览(title 由调用方 debounce;空标题不请求;失败静默 → 上层显示「生成中...」/空)
export function useBranchPreview(title: string) {
  return useQuery({
    queryKey: ['branch-preview', title],
    queryFn: () => requirementsApi.branchPreview(title).then(r => r.data),
    enabled: title.trim().length > 0,
    staleTime: 60_000,
    retry: false,
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
