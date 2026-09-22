/**
 * 四维管理页面包装组件
 * 导出四个路由页面组件,共用 DimensionPage
 */
import { DimensionPage } from './DimensionPage'

// 需求管理:8 种状态
const REQUIREMENT_STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'polishing', label: '打磨中' },
  { value: 'reviewing', label: '评审中' },
  { value: 'approved', label: '已批准' },
  { value: 'in_progress', label: '进行中' },
  { value: 'done', label: '已完成' },
  { value: 'archived', label: '已归档' },
  { value: 'rejected', label: '已取消' },
]

// 任务管理:6 种状态
const TASK_STATUS_OPTIONS = [
  { value: 'pending', label: '待执行' },
  { value: 'running', label: '执行中' },
  { value: 'done', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
  { value: 'timeout', label: '超时' },
]

// 测试管理:3 种状态
const TEST_STATUS_OPTIONS = [
  { value: 'passed', label: '通过' },
  { value: 'failed', label: '失败' },
  { value: 'cases_review', label: '用例评审' },
]

// 发布管理:2 种状态
const RELEASE_STATUS_OPTIONS = [
  { value: 'deployed', label: '已部署' },
  { value: 'failed', label: '失败' },
]

export function RequirementsManage() {
  return <DimensionPage dimension="requirements" title="需求管理" statusOptions={REQUIREMENT_STATUS_OPTIONS} />
}

export function TasksManage() {
  return <DimensionPage dimension="dev" title="任务管理" statusOptions={TASK_STATUS_OPTIONS} />
}

export function TestsManage() {
  return <DimensionPage dimension="test" title="测试管理" statusOptions={TEST_STATUS_OPTIONS} />
}

export function ReleasesManage() {
  return <DimensionPage dimension="release" title="发布管理" statusOptions={RELEASE_STATUS_OPTIONS} />
}
