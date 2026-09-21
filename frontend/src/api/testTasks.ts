/**
 * testTasks — 测试任务相关 API(confirm-cases / accept-failure / reject-to-dev)
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

// ---- Types ----
export interface TestCase {
  id: string
  title: string
  steps: string
  expected: string
  status: 'passed' | 'failed' | 'pending'
  log?: string
}

export interface ConfirmCasesPayload {
  test_cases: Array<Pick<TestCase, 'id' | 'title' | 'steps' | 'expected' | 'status'>>
}

export interface AcceptFailurePayload {
  reason: string
}

export interface RejectToDevPayload {
  title: string
  description: string
}

// ---- API functions ----
export async function confirmCases(
  taskId: string,
  payload: ConfirmCasesPayload,
): Promise<void> {
  await api.post(`/tasks/${taskId}/confirm-cases`, payload)
}

export async function acceptFailure(
  taskId: string,
  payload: AcceptFailurePayload,
): Promise<void> {
  await api.post(`/tasks/${taskId}/accept-failure`, payload)
}

export async function rejectToDev(
  taskId: string,
  payload: RejectToDevPayload,
): Promise<{ task_id: string }> {
  const res = await api.post<{ task_id: string }>(
    `/tasks/${taskId}/reject-to-dev`,
    payload,
  )
  return res.data
}

// ---- React Query hooks ----
export function useConfirmCases(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ConfirmCasesPayload) => confirmCases(taskId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['task', taskId] })
    },
  })
}

export function useAcceptFailure(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: AcceptFailurePayload) => acceptFailure(taskId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['task', taskId] })
    },
  })
}

export function useRejectToDev(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: RejectToDevPayload) => rejectToDev(taskId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}
