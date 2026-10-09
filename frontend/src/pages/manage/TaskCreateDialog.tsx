/**
 * TaskCreateDialog — 统一任务创建表单
 * R1:统一 /manage/tasks 页头"新建任务"按钮的创建入口
 * R2:任务类型选择器(dev/test/release)
 * R3.2:可搜索的项目/需求选择器(后端搜索)
 * R4:完整表单结构(项目→需求→类型→标题→描述→类型特有字段)+ 必填校验 + 提交 + 错误提示 + 成功跳详情
 * R5:类型特有字段插槽(当前内联渲染:test 提示文案 / release 部署端口;dev 无,待提取注册表 TaskTypeFields)
 */
import { useCallback, useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { Alert } from '@/components/ui/Alert'
import { SearchableSelect } from '@/components/SearchableSelect'
import type { SearchableSelectOption } from '@/components/SearchableSelect'
import { searchProjects } from '@/api/projects'
import type { ProjectListItem } from '@/api/projects'
import { searchRequirements } from '@/api/requirements'
import type { RequirementListItem } from '@/api/requirements'
import { createTask, getTaskErrorMessage } from '@/api/tasks'
import type { CreateTaskPayload, TaskType } from '@/api/tasks'
import { ApiError } from '@/api/client'

/** R2:任务类型选项(dev/test/release,requirement 不走创建表单)— 文案照 R2 文案清单 */
const TASK_TYPE_OPTIONS: Array<{ label: string; value: Exclude<TaskType, 'requirement'> }> = [
  { label: '开发', value: 'dev' },
  { label: '测试', value: 'test' },
  { label: '发布', value: 'release' },
]

/** R5:release 部署端口合法范围(全平台唯一) */
const PORT_MIN = 10000
const PORT_MAX = 10099

// R3.2:后端列表项 → 选择器选项(项目:名称+描述;需求:标题)
function toProjectOption(p: ProjectListItem): SearchableSelectOption {
  return { value: p.project_id, label: p.name, description: p.description || undefined }
}
function toRequirementOption(r: RequirementListItem): SearchableSelectOption {
  return { value: r.req_id, label: r.title }
}

interface TaskCreateDialogProps {
  open: boolean
  onClose: () => void
  /** 可选：预填项目 ID（项目详情页使用时传入，禁用项目选择器） */
  projectId?: string
}

export function TaskCreateDialog({ open, onClose, projectId }: TaskCreateDialogProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // R3.2:项目/需求选择(保存完整 option,关闭面板后仍能回显 label)
  const [project, setProject] = useState<SearchableSelectOption | null>(null)
  const [requirement, setRequirement] = useState<SearchableSelectOption | null>(null)
  // R2:任务类型(空串 = 未选择,显示 placeholder)
  const [type, setType] = useState<Exclude<TaskType, 'requirement'> | ''>('')
  // R4:公共字段(标题可选,留空取需求标题;描述可选,留空后端生成默认)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  // R22.F4(BUG-088):分支可选输入(独立创建可指定;留空 → base=项目默认分支,work=需求分支)
  const [baseBranch, setBaseBranch] = useState('')
  const [workBranch, setWorkBranch] = useState('')
  // R5:release 类型特有字段(部署端口,字符串暂存便于输入)
  const [deployPort, setDeployPort] = useState('')
  // R4:错误提示(校验失败 / 接口失败统一走 Alert)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // 当传入 projectId 时，初始化项目状态
  useEffect(() => {
    if (open && projectId) {
      // 使用 searchProjects 获取项目信息
      searchProjects(projectId).then((items) => {
        const p = items.find(item => item.project_id === projectId)
        if (p) {
          setProject({ value: p.project_id, label: p.name, description: p.description || undefined })
        }
      })
    }
  }, [open, projectId])

  /** R4:打开对话框时初始化表单状态(表单清空) */
  useEffect(() => {
    if (open) {
      setProject(null)
      setRequirement(null)
      setType('')
      setTitle('')
      setDescription('')
      setBaseBranch('')
      setWorkBranch('')
      setDeployPort('')
      setErrorMsg(null)
    }
  }, [open])

  // R3.2:搜索走后端(debounce 300ms 在 SearchableSelect 内做)
  const fetchProjectOptions = useCallback(
    (q: string) => searchProjects(q).then((items) => items.map(toProjectOption)),
    [],
  )
  const fetchRequirementOptions = useCallback(
    (q: string) =>
      project
        ? searchRequirements(project.value, q).then((items) => items.map(toRequirementOption))
        : Promise.resolve([]),
    [project],
  )

  /** R3.2:切换项目时清空已选需求(需求选择器重置,重新加载该项目需求列表) */
  const handleProjectChange = (option: SearchableSelectOption) => {
    setProject(option)
    setRequirement(null)
  }

  /** R2/R4:切换类型时更新 type 并清空类型特有字段(公共字段保留) */
  const handleTypeChange = (next: Exclude<TaskType, 'requirement'>) => {
    if (next === type) return
    setType(next)
    setDeployPort('')
  }

  // R4:提交(POST /requirements/{req_id}/tasks);成功后关弹窗 + 跳任务详情页 + 刷新列表
  const mutation = useMutation({
    mutationFn: () => {
      const payload: CreateTaskPayload = {
        type: type as Exclude<TaskType, 'requirement'>,
        title: title.trim(),
        description: description.trim(),
      }
      // R22.F4(BUG-088):分支可选,填了才带(留空 → 后端默认 base=项目默认分支,work=需求分支)
      if (baseBranch.trim()) payload.base_branch = baseBranch.trim()
      if (workBranch.trim()) payload.work_branch = workBranch.trim()
      if (type === 'release') payload.deploy_port = Number(deployPort)
      return createTask(requirement!.value, payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['dimension'] })
      queryClient.invalidateQueries({ queryKey: ['tasks', requirement!.value] })
      onClose()
      navigate(`/tasks/${data.task_id}`)
    },
    onError: (err: Error) => {
      const msg = err instanceof ApiError ? getTaskErrorMessage(err.code, err.message) : err.message
      setErrorMsg(`创建失败:${msg || '请重试'}`)
    },
  })

  /** R4:前端必填校验(项目/需求/类型;release 端口格式)→ 拦截并提示,表单保持 */
  const handleSubmit = () => {
    if (!project) {
      setErrorMsg('请选择关联项目')
      return
    }
    if (!requirement) {
      setErrorMsg('请选择关联需求')
      return
    }
    if (!type) {
      setErrorMsg('请选择任务类型')
      return
    }
    if (type === 'release') {
      const n = Number(deployPort)
      if (!deployPort || !Number.isInteger(n) || n < PORT_MIN || n > PORT_MAX) {
        setErrorMsg('部署端口需为 10000-10099')
        return
      }
    }
    setErrorMsg(null)
    mutation.mutate()
  }

  const submitting = mutation.isPending

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      {/* R4 设计规范:对话框宽度 w-[440px] */}
      <DialogContent className="w-[440px]" onClose={onClose}>
        <DialogHeader>
          {/* 文案照 R4 文案清单:对话框标题 "新建任务" */}
          <DialogTitle className="flex items-center gap-2"><Plus size={16} /> 新建任务</DialogTitle>
        </DialogHeader>

        {/* R4 布局:单列,内容区 flex flex-col gap-4 py-2;字段结构 label + 控件 flex-col gap-1.5 */}
        <div className="flex flex-col gap-4 py-2">
          {/* R4:错误提示(校验/接口失败,表单保持) */}
          {errorMsg && (
            <Alert variant="error" onClose={() => setErrorMsg(null)}>{errorMsg}</Alert>
          )}

          {/* R3.2:可搜索项目选择器(文案照 R3.2 文案清单;必填红星) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              关联项目 <span className="text-red-fg">*</span>
            </label>
            <SearchableSelect
              value={project}
              onChange={handleProjectChange}
              fetchOptions={fetchProjectOptions}
              placeholder="请选择项目"
              searchPlaceholder="搜索项目(名称)"
              emptyText="暂无项目,请先创建项目"
              disabled={submitting}
            />
          </div>
          {/* R3.2:可搜索需求选择器(跟随所选项目;未选项目时禁用;必填红星) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              关联需求 <span className="text-red-fg">*</span>
            </label>
            <SearchableSelect
              value={requirement}
              onChange={setRequirement}
              fetchOptions={fetchRequirementOptions}
              disabled={!project || submitting}
              disabledPlaceholder="请先选择项目"
              placeholder="请选择需求"
              searchPlaceholder="搜索需求(标题/描述)"
              emptyText="该项目暂无可选需求"
            />
          </div>
          {/* R2:类型选择器(必填红星) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              任务类型 <span className="text-red-fg">*</span>
            </label>
            <Select
              value={type}
              placeholder="请选择任务类型"
              options={TASK_TYPE_OPTIONS}
              disabled={submitting}
              onChange={(e) => handleTypeChange(e.target.value as Exclude<TaskType, 'requirement'>)}
            />
          </div>
          {/* R4:任务标题(可选,留空默认取需求标题,max 128) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">任务标题</label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="留空默认取需求标题"
              maxLength={128}
              disabled={submitting}
            />
          </div>
          {/* R4:任务描述(可选,留空后端生成默认) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">任务描述</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="本次要让 AI 做什么?"
              rows={3}
              disabled={submitting}
            />
          </div>
          {/* R22.F4(BUG-088):分支可选输入(独立创建可指定;留空 → base=项目默认分支,work=需求分支) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              基准分支 <span className="text-text-muted text-xs">(可选,留空用项目默认分支)</span>
            </label>
            <Input
              type="text"
              value={baseBranch}
              onChange={(e) => setBaseBranch(e.target.value)}
              placeholder="例如: master"
              disabled={submitting}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              工作分支 <span className="text-text-muted text-xs">(可选,留空用需求分支)</span>
            </label>
            <Input
              type="text"
              value={workBranch}
              onChange={(e) => setWorkBranch(e.target.value)}
              placeholder="留空默认使用需求对应分支"
              disabled={submitting}
            />
          </div>
          {/* R5:类型特有字段插槽(按所选类型动态渲染;切换类型时已清空状态)
              dev 无特有字段;test 提示文案;release 部署端口(必填,全平台唯一) */}
          {type === 'test' && (
            <div className="rounded-md border border-border bg-surface-strong px-3 py-2 text-xs text-text-muted">
              AI 基于 PRD 验收标准 + 测试仓库存量用例生成用例,人审后执行
            </div>
          )}
          {type === 'release' && (
            <div className="flex flex-col gap-1.5">
              <label className="block text-sm font-medium text-text">
                部署端口 <span className="text-red-fg">*</span>
              </label>
              <Input
                type="number"
                value={deployPort}
                onChange={(e) => setDeployPort(e.target.value)}
                placeholder="10000-10099"
                min={PORT_MIN}
                max={PORT_MAX}
                disabled={submitting}
              />
              <div className="text-xs text-text-muted">全平台唯一,范围 10000-10099</div>
            </div>
          )}
        </div>

        <DialogFooter>
          {/* R4:取消关闭对话框(重置由 open effect 在下次打开时统一做) */}
          <Button variant="ghost" onClick={onClose} disabled={submitting}>取消</Button>
          <Button variant="primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? '创建中...' : '创建'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
