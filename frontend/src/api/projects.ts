/**
 * Projects API — 项目 CRUD + 仓库绑定/解绑 + react-query hooks
 * 错误码: 2001-2007 透传
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
