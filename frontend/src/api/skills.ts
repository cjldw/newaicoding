/**
 * Skills & MCP Config API — react-query hooks
 * 错误码:
 *  - 17001: JSON 格式错误
 *  - 17002: 已安装过该 Skill
 *  - 17003: 文件格式错误(缺少 YAML frontmatter 的 name 或 description)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from './client'

// ---- Types ----
export interface McpConfig {
  config: {
    mcpServers: Record<string, {
      command?: string
      args?: string[]
      env?: Record<string, string>
    }>
  }
}

export interface McpTemplateParam {
  name: string
  type: 'string' | 'number'
  required?: boolean
  default?: unknown
  sensitive?: boolean
}

export interface McpTemplate {
  name: string
  display_name: string
  description: string
  params: McpTemplateParam[]
}

export interface Skill {
  skill_id: string
  name: string
  description: string
  scope: 'platform' | 'project'
  content?: string
  created_by?: { user_id: string; username: string }
  created_at?: string
  installed_by?: { user_id: string; username: string }
  installed_at?: string
}

// ---- Error codes ----
export const SkillErrorCodes = {
  JSON_FORMAT_ERROR: 17001,
  SKILL_ALREADY_INSTALLED: 17002,
  FILE_FORMAT_ERROR: 17003,
} as const

export function getSkillErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 17001: return `JSON 格式错误:第 ${error.message}`
      case 17002: return '已安装过该 Skill'
      case 17003: return '文件格式错误:缺少 YAML frontmatter 的 name 或 description'
      default: return error.message
    }
  }
  return '操作失败'
}

// ---- API calls ----
export const mcpApi = {
  get: (projectId: string) => api.get<McpConfig>(`/projects/${projectId}/mcp-config`),
  put: (projectId: string, config: McpConfig) =>
    api.put<{ message: string }>(`/projects/${projectId}/mcp-config`, config),
  templates: (projectId: string) =>
    api.get<{ items: McpTemplate[] }>(`/projects/${projectId}/mcp-config/templates`),
}

export const skillsApi = {
  market: () => api.get<{ items: Skill[] }>('/skills'),
  skillDetail: (skillId: string) => api.get<Skill>(`/skills/${skillId}`),
  installed: (projectId: string) =>
    api.get<{ items: Skill[] }>(`/projects/${projectId}/skills`),
  install: (projectId: string, skillId: string) =>
    api.post<{ message: string }>(`/projects/${projectId}/skills`, { skill_id: skillId }),
  upload: (projectId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    // 使用 fetch 直接调用以支持 multipart
    return fetch(`/api/projects/${projectId}/skills/upload`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
      },
      body: formData,
    }).then(r => r.json())
  },
  uninstall: (projectId: string, skillId: string) =>
    api.delete<{ message: string }>(`/projects/${projectId}/skills/${skillId}`),
}

export const adminSkillsApi = {
  list: () => api.get<{ items: Skill[] }>('/admin/skills'),
  create: (data: { name: string; description: string; content: string }) =>
    api.post<Skill>('/admin/skills', data),
  update: (id: string, data: Partial<{ name: string; description: string; content: string }>) =>
    api.patch<Skill>(`/admin/skills/${id}`, data),
  delete: (id: string) => api.delete<{ message: string }>(`/admin/skills/${id}`),
}

// ---- React Query Hooks: MCP ----
export function useMcpConfig(projectId: string) {
  return useQuery({
    queryKey: ['mcp-config', projectId],
    queryFn: () => mcpApi.get(projectId).then(r => r.data),
  })
}

export function useUpdateMcpConfig(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (config: McpConfig) => mcpApi.put(projectId, config).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['mcp-config', projectId] }) },
  })
}

export function useMcpTemplates(projectId: string) {
  return useQuery({
    queryKey: ['mcp-templates', projectId],
    queryFn: () => mcpApi.templates(projectId).then(r => r.data.items),
  })
}

// ---- React Query Hooks: Skills ----
export function useSkillMarket() {
  return useQuery({
    queryKey: ['skill-market'],
    queryFn: () => skillsApi.market().then(r => r.data.items),
  })
}

export function useInstalledSkills(projectId: string) {
  return useQuery({
    queryKey: ['installed-skills', projectId],
    queryFn: () => skillsApi.installed(projectId).then(r => r.data.items),
  })
}

export function useInstallSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (skillId: string) => skillsApi.install(projectId, skillId).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['installed-skills', projectId] }) },
  })
}

export function useUploadSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => skillsApi.upload(projectId, file),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['installed-skills', projectId] }) },
  })
}

export function useUninstallSkill(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (skillId: string) => skillsApi.uninstall(projectId, skillId).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['installed-skills', projectId] }) },
  })
}

// ---- React Query Hooks: Admin Skills ----
export function useAdminSkills() {
  return useQuery({
    queryKey: ['admin-skills'],
    queryFn: () => adminSkillsApi.list().then(r => r.data.items),
  })
}

export function useCreateAdminSkill() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; description: string; content: string }) =>
      adminSkillsApi.create(data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-skills'] }) },
  })
}

export function useUpdateAdminSkill() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<{ name: string; description: string; content: string }> }) =>
      adminSkillsApi.update(id, data).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-skills'] }) },
  })
}

export function useDeleteAdminSkill() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => adminSkillsApi.delete(id).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-skills'] }) },
  })
}
