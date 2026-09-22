/**
 * Knowledge API — 知识库 + 归档相关接口与 react-query hooks
 * - 归档:GET /api/requirements/{req_id}/archive
 * - 项目知识库:GET/POST /api/projects/{pid}/knowledge
 * - 平台知识库:GET /api/knowledge
 * - 知识条目详情:GET /api/knowledge/{entry_id}
 * - 发布/提升:POST /api/knowledge/{entry_id}/publish, /promote
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

// ---- Types ----
export type KnowledgeType = 'code_snippet' | 'pattern' | 'pitfall' | 'doc'
export type KnowledgeStatus = 'draft' | 'published'

export interface KnowledgeEntry {
  id: number
  entry_id: string
  type: KnowledgeType
  title: string
  content: string
  tags: string[]
  source_links: string[]
  status: KnowledgeStatus
  created_by: { user_id: string; username: string; nickname: string }
  created_at: string
  project_id: string | null
  req_id: string | null
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

export async function fetchKnowledgeDetail(entryId: string): Promise<KnowledgeEntry> {
  const res = await api.get<KnowledgeEntry>(`/knowledge/${entryId}`)
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
