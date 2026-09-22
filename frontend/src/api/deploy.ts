/**
 * Deploy API — 部署相关接口 + react-query hooks
 * - POST /api/tasks/{task_id}/offline 下线部署
 * - GET /api/tasks/check-port?port= 检查端口占用
 * - hostname 校验工具
 */

import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from './client'

// ---- API functions ----
export async function offlineTask(taskId: string): Promise<void> {
  await api.post(`/tasks/${taskId}/offline`)
}

export async function checkPort(port: number): Promise<{ occupied: boolean }> {
  // client.get 不支持 params,手动拼查询串
  const res = await api.get<{ occupied: boolean }>(`/tasks/check-port?port=${port}`)
  return res.data
}

/**
 * hostname 校验:合法主机名(不含协议/路径,支持多级子域)
 * 规则:字母/数字/连字符/点,不能以连字符开头或结尾,总长 ≤253
 */
export function isValidHostname(value: string): boolean {
  if (!value || value.length > 253) return false
  // 不含协议/路径/端口
  if (/[/:#?]/.test(value)) return false
  const labels = value.split('.')
  if (labels.length < 2) return false
  const labelRegex = /^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/
  return labels.every((label) => labelRegex.test(label))
}

// ---- React Query hooks ----
export function useOfflineTask(taskId: string) {
  return useMutation({
    mutationFn: () => offlineTask(taskId),
  })
}

export function useCheckPort(port: number | null) {
  return useQuery({
    queryKey: ['check-port', port],
    queryFn: () => checkPort(port!),
    enabled: port !== null && port >= 10000 && port <= 10099,
    staleTime: 0,
  })
}
