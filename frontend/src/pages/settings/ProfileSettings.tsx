/**
 * 个人资料设置页 — /settings/profile
 * 字段: 昵称 + 头像本地上传(R28:选择文件 → 本地预览 → 上传 → 移除,回退首字母+hash 取色)
 * 由 SettingsLayout 提供左侧导航 + 右侧内容区布局
 */

import { useState, useEffect, type ChangeEvent } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save, User } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Label } from '@/components/ui/Label'
import { Alert } from '@/components/ui/Alert'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/Dialog'
import { usersApi } from '@/api/users'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useToast } from '@/hooks/useToast'
import { getAvColor, getInitial } from '@/utils/avatar'

/** 头像限制(R28):JPG/PNG/WebP,≤ 2MB */
const AVATAR_ACCEPT = 'image/jpeg,image/png,image/webp'
const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const AVATAR_EXTS = ['jpg', 'jpeg', 'png', 'webp']
const AVATAR_MAX_BYTES = 2 * 1024 * 1024

// R28 字段定义:昵称 1-32 字符、不唯一、可为空(清空后回显手机号由后端处理)
const profileSchema = z.object({
  nickname: z.string().max(32, '昵称最多 32 字'),
})

type ProfileFormValues = z.infer<typeof profileSchema>

export function ProfileSettings() {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [, showToast, ToastEl] = useToast()

  // 头像上传状态(R28)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [avatarError, setAvatarError] = useState<string | null>(null)
  const [avatarImgError, setAvatarImgError] = useState(false)
  const [removeOpen, setRemoveOpen] = useState(false)

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

  // avatar_url 变化(上传/移除/刷新)后重置加载失败标记
  useEffect(() => {
    setAvatarImgError(false)
  }, [user?.avatar_url])

  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    values: {
      nickname: user?.nickname ?? '',
    },
  })

  // 昵称保存(R28:仅提交昵称,不再携带头像 URL 表单项)
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

  // 头像上传(R28):成功更新 avatar_url 即时生效,失败提示原因
  const uploadMutation = useMutation({
    mutationFn: usersApi.uploadAvatar,
    onSuccess: (res) => {
      if (user) setUser({ ...user, avatar_url: res.data.avatar_url })
      queryClient.invalidateQueries({ queryKey: ['me'] })
      setSelectedFile(null)
      setPreviewUrl(null)
      setAvatarError(null)
      showToast('ok', '头像已更新')
    },
    onError: (err: unknown) => {
      const code = err instanceof ApiError ? err.code : null
      if (code === 4001) {
        setAvatarError('仅支持 JPG/PNG/WebP 格式的图片')
      } else if (code === 4002) {
        setAvatarError('图片大小不能超过 2MB')
      } else {
        showToast('err', '上传失败,请重试')
      }
    },
  })

  // 头像移除(R28):PATCH /users/me 传 avatar_url=null
  const removeMutation = useMutation({
    mutationFn: () => usersApi.updateProfile({ avatar_url: null }),
    onSuccess: (res) => {
      setUser(res.data)
      queryClient.invalidateQueries({ queryKey: ['me'] })
      setRemoveOpen(false)
      setAvatarError(null)
    },
    onError: (err: Error) => {
      setRemoveOpen(false)
      showToast('err', err.message || '更新失败')
    },
  })

  const onSubmit = (values: ProfileFormValues) => {
    setErrorMsg(null)
    setSuccessMsg(null)
    mutation.mutate({ nickname: values.nickname })
  }

  /** 文件选择:校验格式/大小 → FileReader 本地预览(即时显示),不合规拒绝并提示 */
  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null
    e.target.value = '' // 允许重复选择同一文件
    setAvatarError(null)
    if (!file) return
    const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (!AVATAR_TYPES.includes(file.type) && !AVATAR_EXTS.includes(ext)) {
      setSelectedFile(null)
      setPreviewUrl(null)
      setAvatarError('仅支持 JPG/PNG/WebP 格式的图片')
      return
    }
    if (file.size > AVATAR_MAX_BYTES) {
      setSelectedFile(null)
      setPreviewUrl(null)
      setAvatarError('图片大小不能超过 2MB')
      return
    }
    setSelectedFile(file)
    const reader = new FileReader()
    reader.onload = () => {
      setPreviewUrl(typeof reader.result === 'string' ? reader.result : null)
    }
    reader.onerror = () => {
      setSelectedFile(null)
      setPreviewUrl(null)
      setAvatarError('上传失败,请重试')
    }
    reader.readAsDataURL(file)
  }

  function handleUpload() {
    if (!selectedFile) return
    uploadMutation.mutate(selectedFile)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-text-muted" />
      </div>
    )
  }

  // 头像显示源:本地预览 > 已保存头像(加载失败回退首字母)
  const displayName = user?.nickname || user?.phone || ''
  const avatarSrc = previewUrl ?? (avatarImgError ? null : user?.avatar_url)

  return (
    <div>
      {/* R2.F8(BUG-UI-068):页头补 page-head + h1 + icon 惯例(与全部主页面统一) */}
      <div className="page-head">
        <h1 className="flex items-center gap-2"><User size={18} /> 个人资料</h1>
      </div>

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
        <form onSubmit={handleSubmit(onSubmit)}>
          {/* 头像(R28 本地上传):flex row,gap 16px,区块下间距 24px;80px 圆形 */}
          <div className="mb-6">
            <div className="space-y-2">
              <Label>头像</Label>
              <div className="flex items-center gap-4">
                {avatarSrc ? (
                  <img
                    key={avatarSrc}
                    src={avatarSrc}
                    alt={previewUrl ? '头像预览' : '头像'}
                    className="block object-cover flex-none"
                    style={{
                      width: 80, height: 80, borderRadius: 999,
                      animation: 'avatarFadeIn .3s ease-out', // 头像预览切换淡入
                    }}
                    onError={() => {
                      if (previewUrl) {
                        // 预览图异常:放弃本次预览,回退已保存头像
                        setSelectedFile(null)
                        setPreviewUrl(null)
                      } else {
                        setAvatarImgError(true) // 头像文件缺失:回退首字母
                      }
                    }}
                  />
                ) : (
                  <div
                    className="grid place-items-center flex-none text-white font-semibold select-none"
                    style={{ width: 80, height: 80, borderRadius: 999, background: getAvColor(displayName), fontSize: 32 }}
                    aria-hidden
                  >
                    {getInitial(displayName)}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-3">
                  {/* 文件选择器隐藏,label 触发(同全局 .btn 外观) */}
                  <label className="btn">
                    选择文件
                    <input
                      type="file"
                      accept={AVATAR_ACCEPT}
                      className="hidden"
                      onChange={handleFileChange}
                    />
                  </label>
                  {/* btn--primary 为 R28 渲染核对类名(globals.css .btn--primary),视觉由全局 .btn-pri 提供 */}
                  <Button
                    type="button"
                    variant="primary"
                    className="btn--primary"
                    disabled={!selectedFile || uploadMutation.isPending}
                    onClick={handleUpload}
                  >
                    {uploadMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                    上传头像
                  </Button>
                  {user?.avatar_url && (
                    <Button
                      type="button"
                      variant="danger"
                      disabled={removeMutation.isPending}
                      onClick={() => setRemoveOpen(true)}
                    >
                      移除头像
                    </Button>
                  )}
                </div>
              </div>
              {avatarError && (
                <p className="text-xs text-red-500" role="alert">{avatarError}</p>
              )}
            </div>
          </div>

          {/* 手机号(只读):区块下间距 16px */}
          <div className="space-y-2 mb-4">
            <Label>手机号</Label>
            <Input value={user?.phone ?? ''} disabled className="bg-surface-strong" />
            <p className="text-xs text-text-muted">手机号不可修改</p>
          </div>

          {/* 昵称:1-32 字符,可为空 */}
          <div className="space-y-2 mb-4">
            <Label htmlFor="nickname">昵称</Label>
            <Input
              id="nickname"
              type="text"
              placeholder="请输入昵称"
              maxLength={32}
              {...register('nickname')}
            />
            {errors.nickname && (
              <p className="text-xs text-red-500">{errors.nickname.message}</p>
            )}
          </div>

          {/* 提交:区块上间距 24px */}
          <Button
            type="submit"
            variant="primary"
            className="w-full gap-2"
            style={{ marginTop: 24 }}
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

      {/* 移除头像确认弹窗(R28) */}
      <Dialog open={removeOpen} onOpenChange={setRemoveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>移除头像</DialogTitle>
            <DialogDescription>确定要移除头像吗?将恢复默认头像。</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setRemoveOpen(false)}>
              取消
            </Button>
            <Button type="button" variant="danger" onClick={() => removeMutation.mutate()}>
              确定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {ToastEl}
    </div>
  )
}
