/**
 * 个人资料设置页 — /settings/profile
 * 字段: 昵称、头像 URL
 * 由 SettingsLayout 提供左侧导航 + 右侧内容区布局
 */

import { useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Label } from '@/components/ui/Label'
import { Alert } from '@/components/ui/Alert'
import { usersApi } from '@/api/users'
import { useAuthStore } from '@/stores/authStore'

const profileSchema = z.object({
  nickname: z.string().min(1, '请输入昵称').max(50, '昵称最多 50 字'),
  avatar_url: z.string().url('请输入有效的 URL').or(z.literal('')).optional(),
})

type ProfileFormValues = z.infer<typeof profileSchema>

export function ProfileSettings() {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // 获取当前用户信息
  const { data: meData, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: usersApi.getMe,
  })

  useEffect(() => {
    if (meData?.data) {
      setUser(meData.data)
    }
  }, [meData, setUser])

  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    values: {
      nickname: user?.nickname ?? '',
      avatar_url: user?.avatar_url ?? '',
    },
  })

  const mutation = useMutation({
    mutationFn: usersApi.updateProfile,
    onSuccess: (res) => {
      setUser(res.data)
      queryClient.invalidateQueries({ queryKey: ['me'] })
      setSuccessMsg('个人资料已更新')
      setTimeout(() => setSuccessMsg(null), 3000)
    },
    onError: (err: Error) => {
      setErrorMsg(err.message || '更新失败')
    },
  })

  const onSubmit = (values: ProfileFormValues) => {
    setErrorMsg(null)
    setSuccessMsg(null)
    mutation.mutate(values)
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
      <h2 className="text-xl font-semibold text-text mb-4">个人资料</h2>

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

      <Card className="p-6">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* 手机号(只读) */}
          <div className="space-y-2">
            <Label>手机号</Label>
            <Input value={user?.phone ?? ''} disabled className="bg-surface-strong" />
            <p className="text-xs text-text-muted">手机号不可修改</p>
          </div>

          {/* 昵称 */}
          <div className="space-y-2">
            <Label htmlFor="nickname">昵称</Label>
            <Input
              id="nickname"
              type="text"
              placeholder="请输入昵称"
              {...register('nickname')}
            />
            {errors.nickname && (
              <p className="text-xs text-red-500">{errors.nickname.message}</p>
            )}
          </div>

          {/* 头像 URL */}
          <div className="space-y-2">
            <Label htmlFor="avatar_url">头像 URL</Label>
            <Input
              id="avatar_url"
              type="url"
              placeholder="https://example.com/avatar.png"
              {...register('avatar_url')}
            />
            {errors.avatar_url && (
              <p className="text-xs text-red-500">{errors.avatar_url.message}</p>
            )}
          </div>

          {/* 提交 */}
          <Button
            type="submit"
            variant="primary"
            className="w-full gap-2"
            disabled={mutation.isPending || !isDirty}
          >
            {mutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            保存修改
          </Button>
        </form>
      </Card>
    </div>
  )
}
