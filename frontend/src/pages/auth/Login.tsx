/**
 * 登录页 — /login
 * 布局: 全屏居中卡片, 手机号+密码表单
 * 验证: zod schema, react-hook-form
 * 交互: 密码可见切换, 错误提示, 登录成功跳转 /
 */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation } from '@tanstack/react-query'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Label } from '@/components/ui/Label'
import { Alert } from '@/components/ui/Alert'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'

const loginSchema = z.object({
  phone: z
    .string()
    .min(1, '请输入手机号')
    .regex(/^1[3-9]\d{9}$/, '手机号格式不正确'),
  password: z
    .string()
    .min(1, '请输入密码')
    .min(8, '密码至少8位'),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function Login() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [showPassword, setShowPassword] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  })

  const mutation = useMutation({
    mutationFn: authApi.login,
    onSuccess: (res) => {
      setAuth(res.data.access_token, res.data.refresh_token, res.data.user)
      navigate('/')
    },
    onError: (err: Error) => {
      setErrorMsg(err.message || '登录失败')
    },
  })

  const onSubmit = (values: LoginFormValues) => {
    setErrorMsg(null)
    mutation.mutate(values)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <Card className="w-full max-w-md p-6">
        {/* Logo + 标题 */}
        <div className="flex flex-col items-center mb-8">
          <img src="/logo.svg" alt="Logo" className="w-12 h-12 mb-4" />
          <h1 className="text-xl font-semibold text-text">登录</h1>
          <p className="text-sm text-text-muted mt-1">登录您的账号以继续</p>
        </div>

        {/* 错误提示 */}
        {errorMsg && (
          <Alert variant="error" onClose={() => setErrorMsg(null)} className="mb-4">
            {errorMsg}
          </Alert>
        )}

        {/* 表单 */}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* 手机号 */}
          <div className="space-y-2">
            <Label htmlFor="phone">手机号</Label>
            <Input
              id="phone"
              type="tel"
              placeholder="请输入手机号"
              autoComplete="tel"
              {...register('phone')}
            />
            {errors.phone && (
              <p className="text-xs text-red-500">{errors.phone.message}</p>
            )}
          </div>

          {/* 密码 */}
          <div className="space-y-2">
            <Label htmlFor="password">密码</Label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? 'text' : 'password'}
                placeholder="请输入密码"
                autoComplete="current-password"
                className="pr-10"
                {...register('password')}
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text transition-colors"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {errors.password && (
              <p className="text-xs text-red-500">{errors.password.message}</p>
            )}
          </div>

          {/* 提交按钮 */}
          <Button
            type="submit"
            variant="primary"
            className="w-full"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                登录中...
              </span>
            ) : (
              '登录'
            )}
          </Button>
        </form>

        {/* 链接 */}
        <div className="flex items-center justify-between mt-4 text-sm">
          <Link
            to="/register"
            className="text-accent hover:text-text transition-colors"
          >
            没有账号?注册
          </Link>
          <Link
            to="/forgot-password"
            className="text-accent hover:text-text transition-colors"
          >
            忘记密码?
          </Link>
        </div>
      </Card>
    </div>
  )
}
