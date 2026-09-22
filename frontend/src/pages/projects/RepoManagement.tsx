/**
 * RepoManagement — 仓库 Tab 内容
 * - 角色徽章: main=primary, test=secondary, docs/other=outline
 * - 主仓库行禁用解绑
 * - 添加仓库对话框 + 解绑确认对话框
 */

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Plus, Unlink, AlertCircle, GitBranch } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { RadioGroup } from '@/components/ui/RadioGroup'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useProjectDetail, useBindRepo, useUnbindRepo, getProjectErrorMessage,
} from '@/api/projects'
import type { ProjectRepo } from '@/api/projects'

// 角色徽章映射
const roleMap: Record<string, { label: string; variant: 'primary' | 'secondary' | 'outline' }> = {
  main: { label: '主仓库', variant: 'primary' },
  test: { label: '测试', variant: 'secondary' },
  docs: { label: '文档', variant: 'outline' },
  other: { label: '其他', variant: 'outline' },
}

// 绑定方式文案
const bindTypeMap: Record<string, string> = {
  auto: '自动创建',
  manual: '手动绑定',
}

// 添加仓库表单 schema
const addRepoSchema = z.object({
  role: z.enum(['test', 'docs', 'other']),
  gitlab_repo_url: z.string().min(1, '仓库 URL 不能为空').url('请输入有效的 URL'),
})

type AddRepoForm = z.infer<typeof addRepoSchema>

interface RepoManagementProps {
  projectId: string
}

export function RepoManagement({ projectId }: RepoManagementProps) {
  const { data: project } = useProjectDetail(projectId)
  const bindRepo = useBindRepo()
  const unbindRepo = useUnbindRepo()

  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [unbindTarget, setUnbindTarget] = useState<ProjectRepo | null>(null)
  const [error, setError] = useState<string | null>(null)

  const repos = project?.repos ?? []

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors },
  } = useForm<AddRepoForm>({
    resolver: zodResolver(addRepoSchema),
    defaultValues: {
      role: 'test',
      gitlab_repo_url: '',
    },
  })

  async function handleAddRepo(values: AddRepoForm) {
    setError(null)
    try {
      await bindRepo.mutateAsync({
        projectId,
        data: { role: values.role, gitlab_repo_url: values.gitlab_repo_url },
      })
      setAddDialogOpen(false)
      reset()
    } catch (err) {
      setError(getProjectErrorMessage(err))
    }
  }

  async function handleUnbind() {
    if (!unbindTarget) return
    setError(null)
    try {
      await unbindRepo.mutateAsync({
        projectId,
        repoId: unbindTarget.repo_id,
      })
      setUnbindTarget(null)
    } catch (err) {
      setError(getProjectErrorMessage(err))
    }
  }

  return (
    <div>
      {/* 页头(对齐 vp:icon + 标题 + sub) */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><GitBranch size={18} /> 仓库</h1>
          <div className="sub">项目关联的 GitLab 仓库:主仓库/测试/文档</div>
        </div>
        <div className="acts">
          <Button variant="primary" onClick={() => setAddDialogOpen(true)}>
            <Plus className="w-4 h-4 mr-1" />
            添加仓库
          </Button>
        </div>
      </div>

      {/* 仓库列表 */}
      {repos.length === 0 ? (
        <div className="text-center py-12 text-text-muted">
          暂无仓库,请添加
        </div>
      ) : (
        <div className="card">
        <div className="scrollx">
        <Table className="tbl">
          <TableHeader>
            <TableRow>
              <TableHead>角色</TableHead>
              <TableHead>仓库 URL</TableHead>
              <TableHead>绑定方式</TableHead>
              <TableHead>绑定时间</TableHead>
              <TableHead className="w-[80px]">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {repos.map((repo) => {
              const role = roleMap[repo.role] ?? roleMap.other
              const isMain = repo.role === 'main'
              return (
                <TableRow key={repo.repo_id}>
                  <TableCell>
                    <Badge variant={role.variant}>{role.label}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-sm">{repo.gitlab_repo_url}</span>
                  </TableCell>
                  <TableCell className="text-text-muted">
                    {bindTypeMap[repo.gitlab_bind_type] ?? repo.gitlab_bind_type}
                  </TableCell>
                  <TableCell className="text-text-muted">
                    {repo.created_at
                      ? new Date(repo.created_at).toLocaleDateString('zh-CN')
                      : '—'}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={isMain}
                      onClick={() => setUnbindTarget(repo)}
                      title={isMain ? '主仓库不可解绑' : '解绑仓库'}
                    >
                      <Unlink className="w-4 h-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        </div>
        </div>
      )}

      {/* 添加仓库对话框 */}
      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加仓库</DialogTitle>
            <DialogDescription>
              绑定一个已有 GitLab 仓库到本项目。每个项目最多 10 个仓库。
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit(handleAddRepo)} className="space-y-4">
            <div className="space-y-1">
              <label className="text-sm font-medium text-text">仓库角色</label>
              <RadioGroup
                name="role"
                options={[
                  { label: '测试', value: 'test' },
                  { label: '文档', value: 'docs' },
                  { label: '其他', value: 'other' },
                ]}
                value={watch('role')}
                onChange={(v) => setValue('role', v as 'test' | 'docs' | 'other')}
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-text">GitLab 仓库 URL *</label>
              <Input
                placeholder="https://gitlab.example.com/group/repo.git"
                {...register('gitlab_repo_url')}
              />
              {errors.gitlab_repo_url && (
                <p className="text-xs text-error">{errors.gitlab_repo_url.message}</p>
              )}
            </div>
            {error && (
              <div className="flex items-start gap-2 p-3 rounded-md bg-error/10 border border-error/20">
                <AlertCircle className="w-4 h-4 text-error mt-0.5 flex-shrink-0" />
                <p className="text-sm text-error">{error}</p>
              </div>
            )}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => { setAddDialogOpen(false); setError(null) }}>
                取消
              </Button>
              <Button type="submit" variant="primary" disabled={bindRepo.isPending}>
                {bindRepo.isPending ? '绑定中...' : '绑定仓库'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 解绑确认对话框 */}
      <Dialog open={!!unbindTarget} onOpenChange={() => { setUnbindTarget(null); setError(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>解绑仓库</DialogTitle>
            <DialogDescription>
              确定要解绑仓库「{unbindTarget?.gitlab_repo_url}」吗?
              {unbindTarget?.role === 'main' ? '主仓库不可解绑。' : '解绑后相关功能将不可用。'}
            </DialogDescription>
          </DialogHeader>
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-md bg-error/10 border border-error/20">
              <AlertCircle className="w-4 h-4 text-error mt-0.5 flex-shrink-0" />
              <p className="text-sm text-error">{error}</p>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => { setUnbindTarget(null); setError(null) }}>
              取消
            </Button>
            <Button
              variant="primary"
              className="bg-error hover:bg-error/90"
              onClick={handleUnbind}
              disabled={unbindRepo.isPending}
            >
              {unbindRepo.isPending ? '解绑中...' : '确认解绑'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
