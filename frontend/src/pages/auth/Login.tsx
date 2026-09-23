/**
 * 登录页 — /login
 * 视觉对齐 vp 原型 pageLogin: login-wrap > login-card > login-logo + login-box
 * 保留原有 react-hook-form + zod + useMutation 登录逻辑,只换外壳与类名
 */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation } from '@tanstack/react-query'
import { Eye, EyeOff, Loader2, Key } from 'lucide-react'
import { Input } from '@/components/ui/Input'
import { Alert } from '@/components/ui/Alert'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'
import { AuthLogo } from './AuthLogo'

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
    <div className="login-wrap">
      <div className="login-card">
        {/* Logo 统一组件(R1.F2:LOGO 图居中,与注册/找回/重置页一致) */}
        <AuthLogo />

        {/* 登录卡片 */}
        <div className="login-box">
          <div>
            <h2 style={{ fontSize: 17, marginBottom: 4 }}>登录</h2>
          </div>

          {/* 错误提示 */}
          {errorMsg && (
            <Alert variant="error" onClose={() => setErrorMsg(null)}>
              {errorMsg}
            </Alert>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-[14px]">
            {/* 手机号 */}
            <div className="field">
              <label>手机号</label>
              <Input
                className="input"
                type="tel"
                placeholder="请输入手机号"
                autoComplete="tel"
                {...register('phone')}
              />
              {errors.phone && (
                <div className="hint" style={{ color: 'var(--red-tx, #b91c1c)' }}>
                  {errors.phone.message}
                </div>
              )}
            </div>

            {/* 密码 */}
            <div className="field">
              <label>密码</label>
              <div className="relative">
                <Input
                  className="input"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="请输入密码"
                  autoComplete="current-password"
                  style={{ paddingRight: 36 }}
                  {...register('password')}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
                  style={{
                    position: 'absolute',
                    right: 10,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: 'var(--muted)',
                  }}
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" />
                  ) : (
                    <Eye className="w-4 h-4" />
                  )}
                </button>
              </div>
              {errors.password ? (
                <div className="hint" style={{ color: 'var(--red-tx, #b91c1c)' }}>
                  {errors.password.message}
                </div>
              ) : (
                <div className="hint">5 次错误将锁定 10 分钟</div>
              )}
            </div>

            {/* 提交按钮 */}
            <button
              type="submit"
              className="btn btn-pri"
              style={{ justifyContent: 'center' }}
              disabled={mutation.isPending}
            >
              {mutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <Key className="w-4 h-4" />
                  进入平台
                </>
              )}
            </button>
          </form>
        </div>

        {/* 辅助链接 */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginTop: 10,
            fontSize: 12,
          }}
        >
          <Link to="/register" style={{ color: 'var(--accent)' }}>
            没有账号?注册
          </Link>
          <Link to="/forgot-password" style={{ color: 'var(--accent)' }}>
            忘记密码?
          </Link>
        </div>
      </div>
    </div>
  )
}
