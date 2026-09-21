/**
 * GitLab Token 设置页 — /settings/gitlab-token
 * 显示绑定状态, 支持绑定/解绑操作
 * 由 SettingsLayout 提供左侧导航 + 右侧内容区布局
 */

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Link2, Unlink, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Label } from '@/components/ui/Label'
import { Alert } from '@/components/ui/Alert'
import { Badge } from '@/components/ui/Badge'
import { usersApi } from '@/api/users'

const bindSchema = z.object({
  token: z.string().min(1, '请输入 GitLab Personal Access Token'),
})

type BindFormValues = z.infer<typeof bindSchema>

export function GitLabTokenSettings() {
  const queryClient = useQueryClient()
  const [showToken, setShowToken] = useState(false)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // 查询绑定状态
  const { data: statusData, isLoading } = useQuery({
    queryKey: ['gitlab-token-status'],
    queryFn: usersApi.getGitLabTokenStatus,
  })

  const status = statusData?.data

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<BindFormValues>({
    resolver: zodResolver(bindSchema),
  })

  // 绑定
  const bindMutation = useMutation({
    mutationFn: usersApi.bindGitLabToken,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gitlab-token-status'] })
      reset()
      setSuccessMsg('GitLab Token 绑定成功')
      setTimeout(() => setSuccessMsg(null), 3000)
    },
    onError: (err: Error) => {
      setErrorMsg(err.message || '绑定失败')
    },
  })

  // 解绑
  const unbindMutation = useMutation({
    mutationFn: usersApi.unbindGitLabToken,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gitlab-token-status'] })
      setSuccessMsg('GitLab Token 已解绑')
      setTimeout(() => setSuccessMsg(null), 3000)
    },
    onError: (err: Error) => {
      setErrorMsg(err.message || '解绑失败')
    },
  })

  const onBind = (values: BindFormValues) => {
    setErrorMsg(null)
    setSuccessMsg(null)
    bindMutation.mutate({ gitlab_token: values.token })
  }

  const onUnbind = () => {
    setErrorMsg(null)
    setSuccessMsg(null)
    unbindMutation.mutate()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-xl font-semibold text-text mb-4">GitLab Token</h2>

      {/* 提示 */}
      {errorMsg && (
        <Alert variant="error" onClose={() => setErrorMsg(null)} className="mb-4">
          {errorMsg}
        </Alert>
      )}
      {successMsg && (
        <Alert variant="success" onClose={() => setSuccessMsg(null)} className="mb-4">
          {successMsg}
        </Alert>
      )}

      {/* 绑定状态 */}
      <Card className="p-6 mb-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-text">绑定状态</p>
            <div className="flex items-center gap-2 mt-1">
              {status?.bound ? (
                <>
                  <Badge variant="success">已绑定</Badge>
                  <span className="text-sm text-text-muted">
                    @{status.gitlab_username}
                  </span>
                </>
              ) : (
                <Badge variant="default">未绑定</Badge>
              )}
            </div>
          </div>
          {status?.bound && (
            <Button
              variant="default"
              className="gap-2 text-red-600 hover:text-red-700"
              onClick={onUnbind}
              disabled={unbindMutation.isPending}
            >
              {unbindMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Unlink className="w-4 h-4" />
              )}
              解绑
            </Button>
          )}
        </div>

        {/* scopes */}
        {status?.bound && status.scopes && status.scopes.length > 0 && (
          <div className="mt-4 pt-4 border-t border-border">
            <p className="text-sm text-text-muted mb-2">Token 权限范围</p>
            <div className="flex flex-wrap gap-2">
              {status.scopes.map((scope) => (
                <Badge key={scope} variant="default">
                  {scope}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* 绑定表单(未绑定时显示) */}
      {!status?.bound && (
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Link2 className="w-5 h-5 text-text" />
            <h3 className="text-lg font-medium text-text">绑定 GitLab Token</h3>
          </div>

          <p className="text-sm text-text-muted mb-4">
            请在 GitLab 中生成 Personal Access Token（需要 api 权限），然后粘贴到下方。
            Token 将以 AES-256-GCM 加密存储，服务端不会明文保存。
          </p>

          <form onSubmit={handleSubmit(onBind)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="token">GitLab Personal Access Token</Label>
              <div className="relative">
                <Input
                  id="token"
                  type={showToken ? 'text' : 'password'}
                  placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"
                  className="pr-10 font-mono text-sm"
                  {...register('token')}
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text transition-colors"
                  onClick={() => setShowToken(!showToken)}
                  aria-label={showToken ? '隐藏 Token' : '显示 Token'}
                >
                  {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {errors.token && (
                <p className="text-xs text-red-500">{errors.token.message}</p>
              )}
            </div>

            <Button
              type="submit"
              variant="primary"
              className="w-full gap-2"
              disabled={bindMutation.isPending}
            >
              {bindMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Link2 className="w-4 h-4" />
              )}
              绑定
            </Button>
          </form>
        </Card>
      )}
    </div>
  )
}
