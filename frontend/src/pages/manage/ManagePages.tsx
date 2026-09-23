/**
 * 四维管理页面包装组件
 * 导出四个路由页面组件,共用 DimensionPage
 */
import { ListChecks, Activity, FlaskConical, Rocket } from 'lucide-react'
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
  // icon/desc 照抄 vp pageManage conf(L1665)
  return (
    <DimensionPage
      dimension="requirements"
      title="需求管理"
      statusOptions={REQUIREMENT_STATUS_OPTIONS}
      icon={ListChecks}
      createLabel="新建需求"
      desc="成员项目全量需求汇总 · 与工作台口径不同:此处不限「我创建的」(R22)"
    />
  )
}

export function TasksManage() {
  return (
    <DimensionPage
      dimension="dev"
      title="任务管理"
      statusOptions={TASK_STATUS_OPTIONS}
      icon={Activity}
      createLabel="新建任务"
      desc="成员项目全量任务(四种类型)· 固定按更新时间倒序"
    />
  )
}

export function TestsManage() {
  return (
    <DimensionPage
      dimension="test"
      title="测试管理"
      statusOptions={TEST_STATUS_OPTIONS}
      icon={FlaskConical}
      createLabel="新建测试任务"
      desc="成员项目全量测试任务(type=test)· 前置:至少一个开发任务 done"
    />
  )
}

export function ReleasesManage() {
  return (
    <DimensionPage
      dimension="release"
      title="发布管理"
      statusOptions={RELEASE_STATUS_OPTIONS}
      icon={Rocket}
      createLabel="新建发布任务"
      desc="成员项目全量发布任务(type=release)· 前置:至少一个测试 passed + 端口全平台唯一"
    />
  )
}
