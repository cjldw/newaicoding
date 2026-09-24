/**
 * ProjectCreate — 新建项目对话框
 * - zod 校验: name 必填, slug 自动生成 kebab-case
 * - Radio auto/manual 联动 URL 输入框
 * - 实时 slug 预览
 * - 错误码对应文案
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { RadioGroup } from '@/components/ui/RadioGroup'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import { useCreateProject, getProjectErrorMessage } from '@/api/projects'
import type { CreateProjectRequest } from '@/api/projects'

// kebab-case 转换: 中文转拼音首字母暂不支持,只处理英文/数字/空格/横线
function toKebabCase(str: string): string {
  return str
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

const formSchema = z.object({
  name: z.string().min(1, '项目名称不能为空').max(100, '项目名称不能超过 100 个字符'),
  description: z.string().max(500, '描述不能超过 500 个字符').optional(),
  visibility: z.enum(['private', 'internal']),
  bind_type: z.enum(['auto', 'manual']),
  gitlab_repo_url: z.string().optional(),
})

type FormValues = z.infer<typeof formSchema>

export function ProjectCreate() {
  const navigate = useNavigate()
  const createProject = useCreateProject()
  const [error, setError] = useState<string | null>(null)
  const [slugPreview, setSlugPreview] = useState('')

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: '',
      description: '',
      visibility: 'private',
      bind_type: 'auto',
      gitlab_repo_url: '',
    },
  })

  const nameValue = watch('name')
  const bindType = watch('bind_type')

  // 实时 slug 预览
  useEffect(() => {
    setSlugPreview(toKebabCase(nameValue))
  }, [nameValue])

  async function onSubmit(values: FormValues) {
    setError(null)
    const payload: CreateProjectRequest = {
      name: values.name,
      description: values.description || undefined,
      visibility: values.visibility,
      main_repo: {
        bind_type: values.bind_type,
        ...(values.bind_type === 'manual' ? { gitlab_repo_url: values.gitlab_repo_url } : {}),
      },
    }
    try {
      const result = await createProject.mutateAsync(payload)
      navigate(`/projects/${result.project_id}`)
    } catch (err) {
      setError(getProjectErrorMessage(err))
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) navigate('/projects') }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>新建项目</DialogTitle>
          <DialogDescription>
            创建新项目并绑定主仓库。auto 模式将自动在 GitLab 创建仓库,manual 模式需填写已有仓库 URL。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* 项目名称 */}
          <div className="space-y-1">
            <label className="text-sm font-medium text-text">项目名称 *</label>
            <Input
              placeholder="例如:我的项目"
              {...register('name')}
            />
            {errors.name && (
              <p className="text-xs text-red-fg">{errors.name.message}</p>
            )}
            {slugPreview && (
              <p className="text-xs text-text-muted">
                项目标识:<span className="font-mono ml-1">{slugPreview}</span>
              </p>
            )}
          </div>

          {/* 描述 */}
          <div className="space-y-1">
            <label className="text-sm font-medium text-text">描述</label>
            <Textarea
              placeholder="简要描述项目用途(可选)"
              {...register('description')}
            />
            {errors.description && (
              <p className="text-xs text-red-fg">{errors.description.message}</p>
            )}
          </div>

          {/* 可见性 */}
          <div className="space-y-1">
            <label className="text-sm font-medium text-text">可见性</label>
            <RadioGroup
              name="visibility"
              options={[
                { label: '私有', value: 'private' },
                { label: '内部可见', value: 'internal' },
              ]}
              value={watch('visibility')}
              onChange={(v) => setValue('visibility', v as 'private' | 'internal')}
            />
          </div>

          {/* 仓库绑定方式 */}
          <div className="space-y-1">
            <label className="text-sm font-medium text-text">主仓库绑定方式</label>
            <RadioGroup
              name="bind_type"
              options={[
                { label: '自动创建', value: 'auto' },
                { label: '绑定已有仓库', value: 'manual' },
              ]}
              value={bindType}
              onChange={(v) => setValue('bind_type', v as 'auto' | 'manual')}
            />
          </div>

          {/* manual 模式显示 URL 输入 */}
          {bindType === 'manual' && (
            <div className="space-y-1">
              <label className="text-sm font-medium text-text">GitLab 仓库 URL *</label>
              <Input
                placeholder="https://gitlab.example.com/group/repo.git"
                {...register('gitlab_repo_url')}
              />
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-md bg-red-bg border border-red-border">
              <AlertCircle className="w-4 h-4 text-red-fg mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-fg">{error}</p>
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => navigate('/projects')}
            >
              取消
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={createProject.isPending}
            >
              {createProject.isPending ? '创建中...' : '创建项目'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
