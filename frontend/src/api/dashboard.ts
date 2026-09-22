/**
 * api/dashboard.ts — R21 工作台汇总 + R22 四维列表客户端
 */
import { useQuery } from '@tanstack/react-query'
import { api } from './client'

// ---- Types ----
export interface DashboardProjectRef {
  project_id: string
  name: string
}

export interface RecentRequirement {
  req_id: string
  title: string
  status: string
  project: DashboardProjectRef
  updated_at: string
}

export interface RecentTask {
  task_id: string
  title: string
  status: string
  type?: string
  project: DashboardProjectRef
  updated_at: string
}

export interface DashboardBlock {
  total: number
  by_status: Record<string, number>
  recent: RecentRequirement[] | RecentTask[]
}

export interface DashboardSummary {
  requirements: DashboardBlock
  dev_tasks: DashboardBlock
  test_tasks: DashboardBlock
  release_tasks: DashboardBlock
}

export interface DimensionItem {
  key: string
  title: string
  status: string
  priority?: string
  project: DashboardProjectRef
  updated_at: string
}

export interface DimensionListResponse {
  items: DimensionItem[]
  total: number
  page: number
  page_size: number
}

// ---- Hooks ----
export function useDashboardSummary(enabled = true) {
  return useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: async () => {
      const res = await api.get('/dashboard/summary')
      return (res as any).data as DashboardSummary
    },
    enabled,
  })
}

export function useDimensionList(
  dimension: 'requirements' | 'dev' | 'test' | 'release',
  params: { status?: string; page?: number; page_size?: number },
  enabled = true,
) {
  return useQuery({
    queryKey: ['dimension', dimension, params],
    queryFn: async () => {
      const qs = new URLSearchParams()
      if (params.status) qs.set('status', params.status)
      qs.set('page', String(params.page ?? 1))
      qs.set('page_size', String(params.page_size ?? 20))
      const path =
        dimension === 'requirements'
          ? `/dashboard/requirements?${qs.toString()}`
          : `/dashboard/tasks/${dimension}?${qs.toString()}`
      const res = await api.get(path)
      return (res as any).data as DimensionListResponse
    },
    enabled,
  })
}
