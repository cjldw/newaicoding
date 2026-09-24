/**
 * useTourSteps — R29 平台导览步骤动态生成
 * 数据链(依分片接口契约,复用现有接口):项目 → 第一个项目的需求 → 第一条需求的任务+归档
 * 降级规则:某维度 API 失败或无数据 → 该维度步骤不显示,不阻塞其他维度
 * (链式依赖级联:项目失败则需求/任务/归档均不可得,仅剩 always 步骤,与分片错误处理行一致)
 * 缓存:react-query 管理,弹窗重开不重复请求
 */
import { useQuery } from '@tanstack/react-query'
import { projectsApi, type ProjectListItem } from '@/api/projects'
import { requirementsApi, type RequirementListItem } from '@/api/requirements'
import { fetchTasks, type TaskListItem } from '@/api/tasks'
import { fetchArchive } from '@/api/knowledge'
import { useAuthStore } from '@/stores/authStore'

export interface TourStep {
  n: number // 编号(1-N 动态重排,条件步骤缺失不留空洞)
  title: string
  link: string
}

export function useTourSteps() {
  const user = useAuthStore((s) => s.user)
  const isSuperadmin = user?.role === 'superadmin'

  // 维度1:项目(取第一条)
  const projectsQuery = useQuery({
    queryKey: ['tour-projects'],
    queryFn: () => projectsApi.list({ page: 1, page_size: 1 }).then((r) => r.data),
    staleTime: 60_000,
    retry: false,
  })
  const project: ProjectListItem | undefined = projectsQuery.data?.items[0]

  // 维度2:需求(第一个项目下取第一条;无项目则不请求)
  const reqsQuery = useQuery({
    queryKey: ['tour-reqs', project?.project_id],
    queryFn: () => requirementsApi.list(project!.project_id, { page: 1, page_size: 1 }).then((r) => r.data),
    enabled: !!project,
    staleTime: 60_000,
    retry: false,
  })
  const requirement: RequirementListItem | undefined = reqsQuery.data?.items[0]

  // 维度3-5:任务(第一条需求下一次请求,按 type 筛 dev/test/release 各取一条)
  const tasksQuery = useQuery({
    queryKey: ['tour-tasks', requirement?.req_id],
    queryFn: () => fetchTasks(requirement!.req_id),
    enabled: !!requirement,
    staleTime: 60_000,
    retry: false,
  })
  const tasks: TaskListItem[] = tasksQuery.data?.items ?? []
  const devTask = tasks.find((t) => t.type === 'dev')
  const testTask = tasks.find((t) => t.type === 'test')
  const releaseTask = tasks.find((t) => t.type === 'release')

  // 维度6:归档(第一条需求;请求成功即视为存在已归档需求,404/失败则步骤隐藏)
  const archiveQuery = useQuery({
    queryKey: ['tour-archive', requirement?.req_id],
    queryFn: () => fetchArchive(requirement!.req_id),
    enabled: !!requirement,
    staleTime: 60_000,
    retry: false,
  })

  // 按分片枚举表顺序拼装条件步骤,再 1-N 动态重排编号
  const steps: TourStep[] = [
    { title: '工作台 · Dashboard', link: '/' },
    { title: '四维管理 · 需求管理', link: '/manage/requirements' },
    ...(project
      ? [{ title: `项目 · ${project.name}`, link: `/projects/${project.project_id}` }]
      : []),
    ...(requirement
      ? [{ title: `需求 · ${requirement.title}`, link: `/requirements/${requirement.req_id}` }]
      : []),
    ...(devTask ? [{ title: '开发工作台', link: `/tasks/${devTask.task_id}` }] : []),
    ...(testTask ? [{ title: '测试任务', link: `/tasks/${testTask.task_id}` }] : []),
    ...(releaseTask ? [{ title: '发布任务', link: `/tasks/${releaseTask.task_id}` }] : []),
    ...(requirement && archiveQuery.data
      ? [{ title: '归档时间线', link: `/requirements/${requirement.req_id}/archive` }]
      : []),
    { title: '知识条目', link: '/knowledge' },
    ...(isSuperadmin ? [{ title: '用户管理 / 审计日志', link: '/admin/users' }] : []),
  ].map((s, i) => ({ ...s, n: i + 1 }))

  return { steps }
}
