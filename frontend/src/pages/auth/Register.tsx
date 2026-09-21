/**
 * 注册页 — /register
 * 字段: 手机号、密码、确认密码、邀请码
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

const registerSchema = z
  .object({
    phone: z
      .string()
      .min(1, '请输入手机号')
      .regex(/^1[3-9]\d{9}$/, '手机号格式不正确'),
    password: z
      .string()
      .min(1, '请输入密码')
      .min(8, '密码至少8位'),
    confirmPassword: z.string().min(1, '请确认密码'),
    inviteCode: z.string().min(1, '请输入邀请码'),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: '两次密码不一致',
    path: ['confirmPassword'],
  })

type RegisterFormValues = z.infer<typeof registerSchema>

export function Register() {
  const navigate = useNavigate()
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
  })

  const mutation = useMutation({
    mutationFn: authApi.register,
    onSuccess: () => {
      setSuccessMsg('注册成功，正在跳转登录…')
      setTimeout(() => navigate('/login'), 1500)
    },
    onError: (err: Error) => {
      setErrorMsg(err.message || '注册失败')
    },
  })

  const onSubmit = (values: RegisterFormValues) => {
    setErrorMsg(null)
    setSuccessMsg(null)
    mutation.mutate({
      phone: values.phone,
      password: values.password,
      invite_code: values.inviteCode,
    })
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <Card className="w-full max-w-md p-6">
        {/* Logo + 标题 */}
        <div className="flex flex-col items-center mb-8">
          <img src="/logo.svg" alt="Logo" className="w-12 h-12 mb-4" />
          <h1 className="text-xl font-semibold text-text">注册</h1>
          <p className="text-sm text-text-muted mt-1">创建您的账号</p>
        </div>

        {/* 提示 */}
        {errorMsg && (
          <Alert variant="error" onClose={() => setErrorMsg(null)} className="mb-4">
            {errorMsg}
          </Alert>
        )}
        {successMsg && (
          <Alert variant="success" className="mb-4">
            {successMsg}
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
                placeholder="请输入密码(至少8位)"
                autoComplete="new-password"
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

          {/* 确认密码 */}
          <div className="space-y-2">
            <Label htmlFor="confirmPassword">确认密码</Label>
            <div className="relative">
              <Input
                id="confirmPassword"
                type={showConfirmPassword ? 'text' : 'password'}
                placeholder="请再次输入密码"
                autoComplete="new-password"
                className="pr-10"
                {...register('confirmPassword')}
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text transition-colors"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                aria-label={showConfirmPassword ? '隐藏密码' : '显示密码'}
              >
                {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {errors.confirmPassword && (
              <p className="text-xs text-red-500">{errors.confirmPassword.message}</p>
            )}
          </div>

          {/* 邀请码 */}
          <div className="space-y-2">
            <Label htmlFor="inviteCode">邀请码</Label>
            <Input
              id="inviteCode"
              type="text"
              placeholder="请输入邀请码"
              {...register('inviteCode')}
            />
            {errors.inviteCode && (
              <p className="text-xs text-red-500">{errors.inviteCode.message}</p>
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
                注册中...
              </span>
            ) : (
              '注册'
            )}
          </Button>
        </form>

        {/* 链接 */}
        <div className="flex items-center justify-center mt-4 text-sm">
          <Link
            to="/login"
            className="text-accent hover:text-text transition-colors"
          >
            已有账号?登录
          </Link>
        </div>
      </Card>
    </div>
  )
}
