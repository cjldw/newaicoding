/**
 * KnowledgeBases API — R20 知识库(新)接口与 react-query hooks
 * - 列表/创建:GET/POST /api/projects/{pid}/knowledge-bases
 * - 详情/改名/删除:GET/PATCH/DELETE /api/projects/{pid}/knowledge-bases/{kb_id}
 * - 导入/同步:POST .../{kb_id}/import, .../{kb_id}/sync
 * - 页面树/新建:GET/POST /api/knowledge-bases/{kb_id}/docs
 * - 页面读/改/删:GET/PUT/DELETE /api/knowledge-bases/{kb_id}/docs/{doc_id}
 * - 库内搜索:GET /api/knowledge-bases/{kb_id}/search?q
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from './client'

// ---- Types ----
export type SourceType = 'blank' | 'repo_import'
export type ImportStatus = 'importing' | 'done' | 'failed' | null

export interface KnowledgeBase {
  kb_id: string
  name: string
  description: string | null
  source_type: SourceType
  source_config: RepoSourceConfig | null
  import_status: ImportStatus
  import_error: string | null
  last_synced_at: string | null
  docs_count?: number
}

export interface RepoSourceConfig {
  repo_id: string
  branch: string
  paths: string[]
}

export interface KnowledgeDoc {
  doc_id: string
  kb_id: string
  title: string
  path: string
  content?: string
  sort_order: number
  source_file_path?: string | null
}

export interface DocSearchItem {
  doc_id: string
  title: string
  path: string
  snippet: string // 含 <em> 高亮
}

// ---- API functions ----
export async function fetchKnowledgeBases(pid: string): Promise<{ items: KnowledgeBase[]; total: number }> {
  const res = await api.get<{ items: KnowledgeBase[]; total: number }>(`/projects/${pid}/knowledge-bases`)
    return (res as any).data
}

export async function createKnowledgeBase(pid: string, payload: {
  name: string; description?: string; source_type: SourceType; source_config?: RepoSourceConfig
}): Promise<KnowledgeBase> {
  try {
    const res = await api.post<KnowledgeBase>(`/projects/${pid}/knowledge-bases`, payload)
      return (res as any).data
  } catch (e: any) {
    throw mapKbError(e)
  }
}

export async function fetchKnowledgeBaseDetail(pid: string, kbId: string): Promise<KnowledgeBase & { docs: Omit<KnowledgeDoc, 'content'>[] }> {
  const res = await api.get(`/projects/${pid}/knowledge-bases/${kbId}`)
  return (res as any).data
}

export async function patchKnowledgeBase(pid: string, kbId: string, payload: { name?: string; description?: string }): Promise<void> {
  await api.patch(`/projects/${pid}/knowledge-bases/${kbId}`, payload)
}

export async function deleteKnowledgeBase(pid: string, kbId: string): Promise<void> {
  await api.delete(`/projects/${pid}/knowledge-bases/${kbId}`)
}

export async function importKnowledgeBase(pid: string, kbId: string): Promise<{ kb_id: string; import_status: string }> {
  try {
    const res = await api.post(`/projects/${pid}/knowledge-bases/${kbId}/import`)
    return (res as any).data
  } catch (e: any) {
    throw mapKbError(e)
  }
}

export async function syncKnowledgeBase(pid: string, kbId: string): Promise<{ kb_id: string; import_status: string }> {
  try {
    const res = await api.post(`/projects/${pid}/knowledge-bases/${kbId}/sync`)
    return (res as any).data
  } catch (e: any) {
    throw mapKbError(e)
  }
}

export async function fetchDocs(kbId: string): Promise<{ items: Omit<KnowledgeDoc, 'content'>[] }> {
  // eslint-disable-next-line
  const res = await api.get(`/knowledge-bases/${kbId}/docs`)
    return (res as any).data
}

export async function createDoc(kbId: string, payload: { title: string; parent_path?: string }): Promise<KnowledgeDoc> {
  try {
    const res = await api.post<KnowledgeDoc>(`/knowledge-bases/${kbId}/docs`, payload)
      return (res as any).data
  } catch (e: any) {
    throw mapKbError(e)
  }
}

export async function fetchDocDetail(kbId: string, docId: string): Promise<KnowledgeDoc> {
  const res = await api.get<KnowledgeDoc>(`/knowledge-bases/${kbId}/docs/${docId}`)
    return (res as any).data
}

export async function putDoc(kbId: string, docId: string, payload: { title?: string; content?: string }): Promise<{ doc_id: string; updated_at: string }> {
  try {
    const res = await api.put(`/knowledge-bases/${kbId}/docs/${docId}`, payload)
      return (res as any).data
  } catch (e: any) {
    throw mapKbError(e)
  }
}

export async function deleteDoc(kbId: string, docId: string): Promise<void> {
  try {
    await api.delete(`/knowledge-bases/${kbId}/docs/${docId}`)
  } catch (e: any) {
    throw mapKbError(e)
  }
}

export async function searchDocs(kbId: string, q: string, page = 1, pageSize = 20): Promise<{ items: DocSearchItem[]; total: number }> {
  const res = await api.get(`/knowledge-bases/${kbId}/search?q=${encodeURIComponent(q)}&page=${page}&page_size=${pageSize}`)
    return (res as any).data
}

// ---- Error mapping ----
function mapKbError(e: any): Error {
  if (e instanceof ApiError) {
    const msg = errorCodeMsg(e.code)
    if (msg) return new Error(msg)
  }
  return e
}

function errorCodeMsg(code: number): string | null {
  switch (code) {
    case 20001: return '名称已存在'
    case 20002: return '无权限执行此操作'
    case 20003: return '页面数已达上限'
    case 20005: return '配置无效'
    case 20007: return '导入进行中,请稍候'
    default: return null
  }
}

// ---- Hooks ----
export function useKnowledgeBases(pid: string) {
  return useQuery({
    queryKey: ['knowledge-bases', pid],
    queryFn: () => fetchKnowledgeBases(pid),
    enabled: !!pid,
  })
}

export function useCreateKnowledgeBase(pid: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: { name: string; description?: string; source_type: SourceType; source_config?: RepoSourceConfig }) =>
      createKnowledgeBase(pid, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['knowledge-bases', pid] }) },
  })
}

export function useKnowledgeBaseDetail(pid: string, kbId: string) {
  return useQuery({
    queryKey: ['kb-detail', pid, kbId],
    queryFn: () => fetchKnowledgeBaseDetail(pid, kbId),
    enabled: !!pid && !!kbId,
  })
}

export function useDeleteKnowledgeBase(pid: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (kbId: string) => deleteKnowledgeBase(pid, kbId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['knowledge-bases', pid] }) },
  })
}

export function useSyncKnowledgeBase(pid: string, kbId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => syncKnowledgeBase(pid, kbId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['kb-detail', pid, kbId] }) },
  })
}

export function useDocs(kbId: string) {
  return useQuery({
    queryKey: ['kb-docs', kbId],
    queryFn: () => fetchDocs(kbId),
    enabled: !!kbId,
  })
}

export function useCreateDoc(kbId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: { title: string; parent_path?: string }) => createDoc(kbId, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['kb-docs', kbId] }) },
  })
}

export function useDocDetail(kbId: string, docId: string) {
  return useQuery({
    queryKey: ['kb-doc', kbId, docId],
    queryFn: () => fetchDocDetail(kbId, docId),
    enabled: !!kbId && !!docId,
  })
}

export function usePutDoc(kbId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ docId, ...payload }: { docId: string; title?: string; content?: string }) =>
      putDoc(kbId, docId, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['kb-docs', kbId] }) },
  })
}

export function useDeleteDoc(kbId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (docId: string) => deleteDoc(kbId, docId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['kb-docs', kbId] }) },
  })
}

export function useSearchDocs(kbId: string, q: string) {
  return useQuery({
    queryKey: ['kb-search', kbId, q],
    queryFn: () => searchDocs(kbId, q),
    enabled: !!kbId && !!q && q.length >= 1,
  })
}
