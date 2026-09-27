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

// ---- Skills 市场源(R1)----
// 源清单存 platform_settings 键 skill_market_sources(JSON 数组 [{name,type,base}]);
// GET /skills/market/sources 登录即可读(R4 搜索 Dialog 消费),写沿用 PUT /admin/platform-settings
export type SkillMarketSourceType = 'modelscope' | 'skillssh'

export interface SkillMarketSource {
  name: string
  type: SkillMarketSourceType
  base: string
}

/** 后端未配置该键时的默认两源种子(与后端种子同文案,便于超管直接编辑) */
export const DEFAULT_MARKET_SOURCES: SkillMarketSource[] = [
  { name: 'ModelScope', type: 'modelscope', base: 'https://modelscope.cn' },
  { name: 'skills.sh', type: 'skillssh', base: 'https://skills.sh' },
]

export const marketSourcesApi = {
  get: () => api.get<SkillMarketSource[]>('/skills/market/sources'),
}

// ---- Skills 市场搜索/远程安装(R2/R3)----
// 搜索:GET /skills/market/search?market=&q=(后端代理双市场,归一化+5min 缓存;
//   market 传源 type 值 modelscope/skillssh——R2 契约:请求/响应同值自洽)
// 安装:POST /projects/{pid}/skills/install-remote {market,ref} → 只装 SKILL.md,extra_files 为支撑文件数
export interface MarketSearchItem {
  name: string
  description: string
  installs: number
  ref: string
  market: SkillMarketSourceType
}

export interface MarketSearchData {
  market: string
  items: MarketSearchItem[]
}

export interface InstallRemoteResult {
  skill_id: string
  name: string
  source: 'market'
  source_url: string
  extra_files: number
}

export const skillMarketApi = {
  search: (market: string, q: string) =>
    api.get<MarketSearchData>(
      `/skills/market/search?market=${encodeURIComponent(market)}&q=${encodeURIComponent(q)}`,
    ),
  installRemote: (projectId: string, market: string, ref: string) =>
    api.post<InstallRemoteResult>(`/projects/${projectId}/skills/install-remote`, { market, ref }),
}

// ---- 系统级资产(R6;镜像内置 skills/MCP 快照,只读展示)----
// GET /system-assets(JWT):{collected:true, skills:[{name,detail}], mcps:[{name,detail}],
//   collected_at, image_tag} 或 {collected:false}(未采集引导态)
// POST /admin/system-assets/collect(超管,R5):{skills:n, mcps:n, collected_at, image_tag[, warning]}
export interface SystemAssetEntry {
  name: string
  detail: Record<string, unknown>
}

export interface SystemAssetsData {
  collected: boolean
  skills?: SystemAssetEntry[]
  mcps?: SystemAssetEntry[]
  collected_at?: string
  image_tag?: string
}

export interface CollectSystemAssetsResult {
  skills: number
  mcps: number
  collected_at: string
  image_tag: string
  warning?: string
}

export const systemAssetsApi = {
  get: () => api.get<SystemAssetsData>('/system-assets'),
  collect: () => api.post<CollectSystemAssetsResult>('/admin/system-assets/collect'),
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

// ---- React Query Hooks: 市场源(R1;R4 搜索 Dialog 的源 Select 用)----
export function useMarketSources() {
  return useQuery({
    queryKey: ['skill-market-sources'],
    queryFn: () => marketSourcesApi.get().then(r => r.data),
  })
}

// ---- React Query Hooks: 市场搜索(R2;enabled 由调用方把门——q 防抖后非空才发)----
export function useMarketSearch(market: string, q: string, enabled: boolean) {
  return useQuery({
    queryKey: ['skill-market-search', market, q],
    queryFn: () => skillMarketApi.search(market, q).then(r => r.data),
    enabled,
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

// 市场一键安装(R3;成功 invalidate 已装列表——搜索行按 name 命中即标「已安装」)
export function useInstallRemote(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { market: string; ref: string }) =>
      skillMarketApi.installRemote(projectId, v.market, v.ref).then(r => r.data),
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

// ---- React Query Hooks: 系统级资产(R6;项目侧两处只读展示 + 超管采集)----
export function useSystemAssets() {
  return useQuery({
    queryKey: ['system-assets'],
    queryFn: () => systemAssetsApi.get().then(r => r.data),
  })
}

// 采集成功 invalidate 列表(SkillsMarket「系统级已安装」区块自动刷新;17006=探测失败,502 可重试)
export function useCollectSystemAssets() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => systemAssetsApi.collect().then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['system-assets'] }) },
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
