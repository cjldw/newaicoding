/**
 * Knowledge API — 知识库 + 归档相关接口与 react-query hooks
 * - 归档:GET /api/requirements/{req_id}/archive
 * - 项目知识库:GET/POST /api/projects/{pid}/knowledge
 * - 平台知识库:GET /api/knowledge
 * - 知识条目详情:GET /api/knowledge/{entry_id}(R2:返回 content/source_links + permissions 预埋)
 * - 代码引用:GET /api/knowledge/{entry_id}/code?path={path}(&refresh=1 穿透缓存)
 * - 发布/提升:POST /api/knowledge/{entry_id}/publish, /promote
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

// ---- Types ----
export type KnowledgeType = 'code_snippet' | 'pattern' | 'pitfall' | 'doc'
export type KnowledgeStatus = 'draft' | 'published'

/** R1:A 型条目的 source_links 代码引用对象(同 repo 同 branch,paths 1-10) */
export interface KnowledgeCodeSource {
  type: 'code'
  repo_id: string
  branch: string
  paths: string[]
}

/** source_links 元素:历史 URL 字符串 | R1 code 对象 */
export type KnowledgeSourceLink = string | KnowledgeCodeSource

export function isCodeSource(link: KnowledgeSourceLink): link is KnowledgeCodeSource {
  return typeof link === 'object' && link !== null && (link as KnowledgeCodeSource).type === 'code'
}

/** R3 预埋:详情接口 permissions(后端算好,前端零猜测直接消费;未返回时容错缺省) */
export interface KnowledgePermissions {
  can_edit?: boolean
  can_delete?: boolean
  editable_fields?: string[]
}

export interface KnowledgeEntry {
  id: number
  entry_id: string
  type: KnowledgeType
  title: string
  content: string
  tags: string[]
  source_links: KnowledgeSourceLink[]
  status: KnowledgeStatus
  created_by: { user_id: string; username: string; nickname: string }
  created_at: string
  project_id: string | null
  req_id: string | null
}

/** R2:详情响应(列表 brief + content/source_links,后端增强后另带 permissions) */
export type KnowledgeEntryDetail = KnowledgeEntry & {
  permissions?: KnowledgePermissions
}

// ---- R2 代码引用接口类型(照分片契约) ----
/** 目录递归树节点:文本文件带 content(一次带回);二进制文件只列节点无 content */
export interface KnowledgeCodeFileNode {
  path: string
  kind: 'file' | 'dir'
  size?: number
  content?: string | null
  binary?: boolean
  children?: KnowledgeCodeFileNode[]
}

export interface KnowledgeCodeResponse {
  path: string
  kind: 'file' | 'dir'
  content?: string
  tree?: KnowledgeCodeFileNode[]
  size?: number
  /** 目录递归超 200 文件截断时为 true(前端区顶提示) */
  partial?: boolean
  /** 截断原因:count=超 200 文件 / size=响应体超 10MB(随 partial=true 返回) */
  partial_reason?: 'count' | 'size'
  /** 容错:后端若随响应回源标注则直接采用 */
  repo_name?: string
  branch?: string
}

export interface ArchiveTimelineNode {
  type: string
  description: string
  created_at: string
  operator?: string
}

export interface ArchiveData {
  timeline: ArchiveTimelineNode[]
  summary_file_path: string | null
  requirement: {
    title: string
    status: string
    created_by: { user_id: string; username: string; nickname: string }
    created_at: string
  }
  knowledge_entries: KnowledgeEntry[]
}

export interface KnowledgeListResponse {
  items: KnowledgeEntry[]
  total: number
}

export interface KnowledgeListParams {
  q?: string
  tag?: string
  type?: KnowledgeType
  page?: number
  page_size?: number
}

export interface CreateKnowledgePayload {
  type: KnowledgeType
  title: string
  content: string
  tags: string[]
  source_links?: string[]
}

// ---- API functions ----
export async function fetchArchive(reqId: string): Promise<ArchiveData> {
  const res = await api.get<ArchiveData>(`/requirements/${reqId}/archive`)
  return res.data
}

export async function fetchProjectKnowledge(
  pid: string,
  params: KnowledgeListParams = {},
): Promise<KnowledgeListResponse> {
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.tag) qs.set('tag', params.tag)
  if (params.type) qs.set('type', params.type)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  const query = qs.toString()
  const res = await api.get<KnowledgeListResponse>(
    `/projects/${pid}/knowledge${query ? `?${query}` : ''}`,
  )
  return res.data
}

export async function fetchPlatformKnowledge(
  params: KnowledgeListParams = {},
): Promise<KnowledgeListResponse> {
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.tag) qs.set('tag', params.tag)
  if (params.type) qs.set('type', params.type)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  const query = qs.toString()
  const res = await api.get<KnowledgeListResponse>(
    `/knowledge${query ? `?${query}` : ''}`,
  )
  return res.data
}

export async function fetchKnowledgeDetail(entryId: string): Promise<KnowledgeEntryDetail> {
  const res = await api.get<KnowledgeEntryDetail>(`/knowledge/${entryId}`)
  return res.data
}

/** R2:按路径拉代码引用(逐路径请求,失败互不影响;refresh=1 穿透服务端 5 分钟缓存) */
export async function fetchKnowledgeCode(
  entryId: string,
  path: string,
  refresh = false,
): Promise<KnowledgeCodeResponse> {
  const qs = new URLSearchParams({ path })
  if (refresh) qs.set('refresh', '1')
  const res = await api.get<KnowledgeCodeResponse>(
    `/knowledge/${entryId}/code?${qs.toString()}`,
  )
  return res.data
}

export async function createProjectKnowledge(
  pid: string,
  payload: CreateKnowledgePayload,
): Promise<{ entry_id: string }> {
  const res = await api.post<{ entry_id: string }>(
    `/projects/${pid}/knowledge`,
    payload,
  )
  return res.data
}

export async function publishKnowledge(entryId: string): Promise<void> {
  await api.post(`/knowledge/${entryId}/publish`)
}

export async function promoteKnowledge(entryId: string): Promise<void> {
  await api.post(`/knowledge/${entryId}/promote`)
}

// ---- React Query hooks ----
export function useArchive(reqId: string) {
  return useQuery({
    queryKey: ['archive', reqId],
    queryFn: () => fetchArchive(reqId),
    enabled: !!reqId,
  })
}

export function useProjectKnowledge(pid: string, params: KnowledgeListParams = {}) {
  return useQuery({
    queryKey: ['project-knowledge', pid, params],
    queryFn: () => fetchProjectKnowledge(pid, params),
    enabled: !!pid,
  })
}

export function usePlatformKnowledge(params: KnowledgeListParams = {}) {
  return useQuery({
    queryKey: ['platform-knowledge', params],
    queryFn: () => fetchPlatformKnowledge(params),
  })
}

export function useKnowledgeDetail(entryId: string) {
  return useQuery({
    queryKey: ['knowledge', entryId],
    queryFn: () => fetchKnowledgeDetail(entryId),
    enabled: !!entryId,
    // 403/404 等业务错误不重试(R2:非成员访问项目级详情 → 403 直接呈现)
    retry: false,
  })
}

/**
 * R2:代码引用按路径懒加载 hook
 * - enabled 由调用方按「进入视口」控制(逐路径懒加载)
 * - refreshNonce 递增即换 key 强制绕过 react-query 缓存;且仅 nonce 变更后的首次
 *   拉取带 refresh=1(穿透服务端 5 分钟缓存),同一 key 的后续 refetch(窗口聚焦
 *   等触发)回落为普通请求,避免 refresh 粘滞
 */
const refreshedCodeKeys = new Set<string>()

export function useKnowledgeCode(entryId: string, path: string, enabled: boolean, refreshNonce = 0) {
  const key = `${entryId}:${path}:${refreshNonce}`
  return useQuery({
    queryKey: ['knowledge-code', entryId, path, refreshNonce],
    queryFn: () => {
      const withRefresh = refreshNonce > 0 && !refreshedCodeKeys.has(key)
      refreshedCodeKeys.add(key)
      return fetchKnowledgeCode(entryId, path, withRefresh)
    },
    enabled: enabled && !!entryId && !!path,
    retry: false,
  })
}

export function useCreateProjectKnowledge(pid: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateKnowledgePayload) => createProjectKnowledge(pid, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project-knowledge', pid] })
    },
  })
}

export function usePublishKnowledge(entryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => publishKnowledge(entryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', entryId] })
      qc.invalidateQueries({ queryKey: ['project-knowledge'] })
      qc.invalidateQueries({ queryKey: ['platform-knowledge'] })
    },
  })
}

export function usePromoteKnowledge(entryId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => promoteKnowledge(entryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', entryId] })
      qc.invalidateQueries({ queryKey: ['project-knowledge'] })
      qc.invalidateQueries({ queryKey: ['platform-knowledge'] })
    },
  })
}
