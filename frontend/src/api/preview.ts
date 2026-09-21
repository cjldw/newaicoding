/**
 * Preview API — 任务预览轮询 hook
 * - GET /api/tasks/{taskId}/previews
 * - 后端契约: 统一外层 { code, data: { items: [...] }, message }
 * - 3s refetchInterval 轮询,后端他人并行实现
 */
import { useQuery } from '@tanstack/react-query'
import { api } from './client'

export interface PreviewItem {
  port: number
  preview_url: string
  status: 'active' | 'inactive'
}

export interface PreviewsResponse {
  items: PreviewItem[]
}

/** 获取任务预览列表(原始请求) */
export async function fetchTaskPreviews(taskId: string): Promise<PreviewsResponse> {
  const res = await api.get<PreviewsResponse>(`/tasks/${taskId}/previews`)
  return res.data
}

/**
 * useTaskPreviews — react-query 轮询 hook
 * - 3s refetchInterval
 * - 仅当存在 active 预览时返回有效 previewUrl
 */
export function useTaskPreviews(taskId: string | null) {
  return useQuery({
    queryKey: ['task-previews', taskId],
    queryFn: () => fetchTaskPreviews(taskId!),
    enabled: !!taskId,
    refetchInterval: 3000,
    // 取第一个 active 的预览 URL
    select: (data) => {
      const active = data.items?.find((i) => i.status === 'active')
      return active?.preview_url ?? null
    },
  })
}
