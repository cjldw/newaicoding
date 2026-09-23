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

export interface DimensionUserBrief {
  user_id: string
  username: string
  nickname: string | null
}

export interface DimensionItem {
  key: string
  title: string
  status: string
  priority?: string
  /** R22.F2:任务维类型(requirement/dev/test/release) */
  type?: string
  /** R22.F2(BUG-UI-059):需求维专属 */
  req_branch?: string
  /** R22.F2:各维统一创建人摘要 */
  created_by?: DimensionUserBrief
  /** R22.F2(BUG-UI-060):任务 Runner 名称 */
  runner?: string
  /** R22.F2:测试维"用例通过"pass/total(未执行为 null) */
  cases_passed?: string | null
  /** R22.F2:发布维部署信息 */
  deploy_port?: number | null
  deploy_host?: string | null
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
  params: { status?: string; project_id?: string; q?: string; page?: number; page_size?: number },
  enabled = true,
) {
  return useQuery({
    queryKey: ['dimension', dimension, params],
    queryFn: async () => {
      const qs = new URLSearchParams()
      if (params.status) qs.set('status', params.status)
      // R22.F2(BUG-UI-069):项目筛选 + 标题关键字搜索
      if (params.project_id) qs.set('project_id', params.project_id)
      if (params.q) qs.set('q', params.q)
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
