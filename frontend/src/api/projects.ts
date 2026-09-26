/**
 * Projects API — 项目 CRUD + 仓库绑定/解绑 + react-query hooks
 * 错误码: 2001-2007 透传
 */

import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { api, ApiError } from './client'

// ---- Types ----
export interface ProjectOwner {
  user_id: string
  username: string
  nickname: string
}

export interface ProjectListItem {
  project_id: string
  name: string
  slug: string
  description: string
  status: 'active' | 'archived' | 'deleted'
  owner: ProjectOwner
  repo_count: number
  req_count: number // R2.F10(BUG-049):项目需求数
  member_count: number // R2.F10(BUG-049):成员数(含 owner)
  created_at: string
}

export interface ProjectListResponse {
  items: ProjectListItem[]
  total: number
  page: number
  page_size: number
}

export interface ProjectRepo {
  repo_id: string
  role: 'main' | 'test' | 'docs' | 'other'
  gitlab_repo_url: string
  gitlab_repo_id: number
  gitlab_bind_type: 'auto' | 'manual'
  created_at?: string
}

export interface ProjectDetail {
  project_id: string
  name: string
  slug: string
  description: string
  status: 'active' | 'archived' | 'deleted'
  visibility: 'private' | 'internal'
  default_branch: string
  owner: ProjectOwner
  repos: ProjectRepo[]
  created_at: string
  updated_at: string
}

export interface CreateProjectRequest {
  name: string
  description?: string
  visibility: 'private' | 'internal'
  default_branch?: string
  main_repo: {
    bind_type: 'auto' | 'manual'
    gitlab_repo_url?: string
  }
}

export interface CreateProjectResponse {
  project_id: string
  slug: string
  main_repo: {
    repo_id: string
    gitlab_repo_url: string
    gitlab_repo_id: number
  }
}

export interface BindRepoRequest {
  role: 'test' | 'docs' | 'other'
  gitlab_repo_url: string
}

export interface BindRepoResponse {
  repo_id: string
  role: string
  gitlab_repo_url: string
  gitlab_repo_id: number
}

// ---- API calls ----
export const projectsApi = {
  list: (params: { status?: string; page?: number; page_size?: number }) => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.page) query.set('page', String(params.page))
    if (params.page_size) query.set('page_size', String(params.page_size))
    return api.get<ProjectListResponse>(`/projects?${query.toString()}`)
  },
  detail: (projectId: string) => api.get<ProjectDetail>(`/projects/${projectId}`),
  create: (data: CreateProjectRequest) => api.post<CreateProjectResponse>('/projects', data),
  update: (projectId: string, data: Partial<CreateProjectRequest>) =>
    api.patch<ProjectDetail>(`/projects/${projectId}`, data),
  delete: (projectId: string) => api.delete<{ message: string }>(`/projects/${projectId}`),
  archive: (projectId: string) => api.post<{ message: string }>(`/projects/${projectId}/archive`),
  bindRepo: (projectId: string, data: BindRepoRequest) =>
    api.post<BindRepoResponse>(`/projects/${projectId}/repos`, data),
  unbindRepo: (projectId: string, repoId: string) =>
    api.delete<{ message: string }>(`/projects/${projectId}/repos/${repoId}`),
}

// ---- Error code helpers ----
export const ProjectErrorCodes = {
  GITLAB_NOT_CONFIGURED: 2001,
  REPO_URL_INVALID: 2002,
  PROJECT_LIMIT_EXCEEDED: 2003,
  REPO_ALREADY_BOUND: 2004,
  REPO_LIMIT_EXCEEDED: 2005,
  MAIN_REPO_CANNOT_UNBIND: 2006,
  INVALID_CONFIG_VALUE: 2007,
} as const

export function getProjectErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 2001: return '平台 GitLab 未配置,请联系管理员'
      case 2002: return '仓库 URL 无效或无权限'
      case 2003: return '项目数已达上限(50)'
      case 2004: return '该仓库已绑定到本项目'
      case 2005: return '仓库数已达上限(10)'
      case 2006: return '主仓库不可解绑'
      case 2007: return '配置值格式非法'
      default: return error.message
    }
  }
  return '操作失败'
}

// ---- React Query Hooks ----
export function useProjectList(params: { status?: string; page?: number; page_size?: number }) {
  return useQuery({
    queryKey: ['projects', params],
    queryFn: () => projectsApi.list(params).then(r => r.data),
  })
}

export function useProjectDetail(projectId: string) {
  return useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.detail(projectId).then(r => r.data),
    enabled: !!projectId,
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateProjectRequest) => projectsApi.create(data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['projects'] }) },
  })
}

export function useUpdateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: { projectId: string; data: Partial<CreateProjectRequest> }) =>
      projectsApi.update(projectId, data).then(r => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      qc.invalidateQueries({ queryKey: ['project', variables.projectId] })
    },
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (projectId: string) => projectsApi.delete(projectId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['projects'] }) },
  })
}

export function useArchiveProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (projectId: string) => projectsApi.archive(projectId),
    onSuccess: (_data, projectId) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      qc.invalidateQueries({ queryKey: ['project', projectId] })
    },
  })
}

export function useBindRepo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: { projectId: string; data: BindRepoRequest }) =>
      projectsApi.bindRepo(projectId, data).then(r => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['project', variables.projectId] })
    },
  })
}

export function useUnbindRepo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, repoId }: { projectId: string; repoId: string }) =>
      projectsApi.unbindRepo(projectId, repoId),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['project', variables.projectId] })
    },
  })
}

// ---- 仓库分支列表(R1:知识条目「关联代码」创建 Dialog 的分支下拉) ----
export interface RepoBranch {
  name: string
  default: boolean
}

export function useProjectRepoBranches(projectId: string, repoId: string) {
  return useQuery({
    queryKey: ['project-repo-branches', projectId, repoId],
    queryFn: async () => {
      const res = await api.get<RepoBranch[]>(`/projects/${projectId}/repos/${repoId}/branches`)
      return res.data
    },
    enabled: !!projectId && !!repoId,
    retry: false,
  })
}

// ---- 成员管理(R12) ----
export interface ProjectMember {
  user_id: string
  username: string
  nickname: string
  avatar_url: string
  role: 'owner' | 'editor' | 'viewer'
  invited_by: { user_id: string; username: string } | null
  joined_at: string
}

export interface ProjectMembersResponse {
  items: ProjectMember[]
}

export interface ChangeRoleRequest {
  role: 'owner' | 'editor' | 'viewer'
}

export interface TransferOwnershipRequest {
  new_owner_user_id: string
}

// ---- 候选用户列表(R1 成员批量邀请) ----
export interface CandidateUser {
  user_id: string
  /** 打码手机号(mask_phone) */
  phone: string
  nickname: string
  avatar_url: string
  status: 'active' | 'disabled'
  /** 已是项目成员(含 owner)→ 前端禁选 */
  is_member: boolean
}

export interface CandidateUsersResponse {
  items: CandidateUser[]
  total: number
  page: number
  page_size: number
}

export interface CandidateUsersParams {
  q?: string
  page?: number
  page_size?: number
}

// ---- 批量邀请(R2/R3) ----
export interface BatchInviteMemberRequest {
  user_ids: string[]
  role: 'editor' | 'viewer'
}

export interface BatchInviteMemberResponse {
  added: number
  role: 'editor' | 'viewer'
  users: { user_id: string; nickname: string | null }[]
}

/** R2:整批 400 时 data.errors 逐条原因 */
export interface BatchInviteErrorItem {
  user_id: string
  reason: string
}

export const membersApi = {
  list: (projectId: string) =>
    api.get<ProjectMembersResponse>(`/projects/${projectId}/members`),
  candidates: (projectId: string, params: CandidateUsersParams = {}) => {
    const query = new URLSearchParams()
    if (params.q) query.set('q', params.q)
    if (params.page) query.set('page', String(params.page))
    if (params.page_size) query.set('page_size', String(params.page_size))
    return api.get<CandidateUsersResponse>(
      `/projects/${projectId}/candidate-users?${query.toString()}`,
    )
  },
  batch: (projectId: string, data: BatchInviteMemberRequest) =>
    api.post<BatchInviteMemberResponse>(`/projects/${projectId}/members/batch`, data),
  remove: (projectId: string, userId: string) =>
    api.delete<{ message: string }>(`/projects/${projectId}/members/${userId}`),
  changeRole: (projectId: string, userId: string, data: ChangeRoleRequest) =>
    api.patch<ProjectMember>(`/projects/${projectId}/members/${userId}`, data),
  transferOwnership: (projectId: string, data: TransferOwnershipRequest) =>
    api.post<{ message: string }>(`/projects/${projectId}/transfer-ownership`, data),
}

export const MemberErrorCodes = {
  USER_NOT_FOUND: 12001,
  ALREADY_MEMBER: 12002,
  MEMBER_LIMIT_EXCEEDED: 12003,
  LAST_OWNER_REQUIRED: 12004,
  TARGET_NOT_MEMBER: 12005,
} as const

export function getMemberErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 12001: return '该手机号未注册,请联系管理员邀请注册'
      case 12002: return '该用户已是项目成员'
      case 12003: return '项目成员数已达上限(50人)'
      case 12004: return '项目必须至少保留一个所有者'
      case 12005: return '目标用户不是项目成员'
      default: return error.message
    }
  }
  return '操作失败'
}

/** R3:取批量邀请整批 400 的 data.errors(非该形态错误返回 null,走通用 message) */
export function getBatchInviteErrors(error: unknown): BatchInviteErrorItem[] | null {
  if (error instanceof ApiError && error.data && typeof error.data === 'object') {
    const errors = (error.data as { errors?: unknown }).errors
    if (Array.isArray(errors)) {
      return errors.filter(
        (it): it is BatchInviteErrorItem =>
          !!it && typeof it === 'object' &&
          typeof (it as { user_id?: unknown }).user_id === 'string' &&
          typeof (it as { reason?: unknown }).reason === 'string',
      )
    }
  }
  return null
}

export function useProjectMembers(projectId: string) {
  return useQuery({
    queryKey: ['project-members', projectId],
    queryFn: () => membersApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
  })
}

/** 候选用户列表(R3 邀请 Dialog;enabled 由调用方控制,Dialog 关闭不请求) */
export function useCandidateUsers(
  projectId: string,
  params: Required<Pick<CandidateUsersParams, 'q' | 'page'>> & { page_size: number },
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['project-candidate-users', projectId, params.q, params.page, params.page_size],
    queryFn: () =>
      membersApi.candidates(projectId, {
        q: params.q || undefined,
        page: params.page,
        page_size: params.page_size,
      }).then(r => r.data),
    enabled: enabled && !!projectId,
    placeholderData: keepPreviousData,
  })
}

/** 批量邀请(R3):200 invalidate 成员列表+候选列表;400 整批拒绝由调用方取 data.errors 渲染 */
export function useBatchInviteMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: { projectId: string; data: BatchInviteMemberRequest }) =>
      membersApi.batch(projectId, data).then(r => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['project-members'] })
      qc.invalidateQueries({ queryKey: ['project-candidate-users'] })
    },
  })
}

export function useRemoveMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, userId }: { projectId: string; userId: string }) =>
      membersApi.remove(projectId, userId),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['project-members', variables.projectId] })
    },
  })
}

export function useChangeMemberRole() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, userId, data }: {
      projectId: string; userId: string; data: ChangeRoleRequest
    }) => membersApi.changeRole(projectId, userId, data).then(r => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['project-members', variables.projectId] })
    },
  })
}

export function useTransferOwnership() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: { projectId: string; data: TransferOwnershipRequest }) =>
      membersApi.transferOwnership(projectId, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['project-members', variables.projectId] })
      qc.invalidateQueries({ queryKey: ['project', variables.projectId] })
    },
  })
}

// ---- 模型配置(R13) ----
export interface ModelConfig {
  config_id: string
  name: string
  base_url: string
  api_key_masked: string
  model: string
  is_default: boolean
  enabled: boolean
  created_by: {
    user_id: string
    username: string
  }
  created_at: string
}

export interface ModelConfigListResponse {
  items: ModelConfig[]
}

export interface CreateModelConfigRequest {
  name: string
  base_url: string
  api_key: string
  model: string
  is_default: boolean
  enabled: boolean
}

export interface UpdateModelConfigRequest {
  name?: string
  base_url?: string
  api_key?: string
  model?: string
  is_default?: boolean
  enabled?: boolean
}

export interface TestModelConfigRequest {
  base_url: string
  api_key: string
  model: string
}

export interface TestModelConfigResponse {
  success: boolean
  latency_ms: number
}

export const modelConfigsApi = {
  list: (projectId: string) =>
    api.get<ModelConfigListResponse>(`/projects/${projectId}/model-configs`),
  create: (projectId: string, data: CreateModelConfigRequest) =>
    api.post<ModelConfig>(`/projects/${projectId}/model-configs`, data),
  update: (projectId: string, configId: string, data: UpdateModelConfigRequest) =>
    api.patch<ModelConfig>(`/projects/${projectId}/model-configs/${configId}`, data),
  delete: (projectId: string, configId: string) =>
    api.delete<{ message: string }>(`/projects/${projectId}/model-configs/${configId}`),
  test: (projectId: string, data: TestModelConfigRequest) =>
    api.post<TestModelConfigResponse>(`/projects/${projectId}/model-configs/test`, data),
  resolvable: (projectId: string) =>
    api.get<ResolvableResponse>(`/projects/${projectId}/model-configs/resolvable`),
}

export const ModelConfigErrorCodes = {
  CONNECTION_FAILED: 13001,
  NAME_DUPLICATE: 13002,
  DEFAULT_EXISTS: 13003,
  CANNOT_DELETE_DEFAULT: 13004,
} as const

export function getModelConfigErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 13001: return '连接失败,请检查 Base URL 和 API Key'
      case 13002: return '配置名已存在'
      case 13003: return '已有默认配置,请先取消原默认'
      case 13004: return '不可删除默认配置,请先指定新默认'
      default: return error.message
    }
  }
  return '操作失败'
}

export function useModelConfigs(projectId: string) {
  return useQuery({
    queryKey: ['model-configs', projectId],
    queryFn: () => modelConfigsApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
  })
}

export function useCreateModelConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }: { projectId: string; data: CreateModelConfigRequest }) =>
      modelConfigsApi.create(projectId, data).then(r => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['model-configs', variables.projectId] })
    },
  })
}

export function useUpdateModelConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, configId, data }: {
      projectId: string; configId: string; data: UpdateModelConfigRequest
    }) => modelConfigsApi.update(projectId, configId, data).then(r => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['model-configs', variables.projectId] })
    },
  })
}

export function useDeleteModelConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, configId }: { projectId: string; configId: string }) =>
      modelConfigsApi.delete(projectId, configId),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['model-configs', variables.projectId] })
    },
  })
}

export function useTestModelConfig() {
  return useMutation({
    mutationFn: ({ projectId, data }: { projectId: string; data: TestModelConfigRequest }) =>
      modelConfigsApi.test(projectId, data).then(r => r.data),
  })
}

// ---- 生效配置查询(R23) ----
export interface ResolvableResponse {
  effective_source: 'project' | 'platform' | 'none'
  base_url: string | null
  model: string | null
  api_key_masked: string | null
}

export function useResolvableModelConfig(projectId: string) {
  return useQuery({
    queryKey: ['model-configs-resolvable', projectId],
    queryFn: () => modelConfigsApi.resolvable(projectId).then(r => r.data),
    enabled: !!projectId,
  })
}
