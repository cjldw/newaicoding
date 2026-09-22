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
        {/* Logo + 品牌副标题 */}
        <div className="login-logo">
          <span
            className="logo-mark"
            style={{
              width: 38,
              height: 38,
              borderRadius: 10,
              display: 'grid',
              placeItems: 'center',
              background: 'var(--primary)',
              color: '#fff',
              fontWeight: 700,
              fontSize: 18,
            }}
          >
            旗
          </span>
          <span>
            <b style={{ fontSize: 18 }}>旗程</b>
            <span
              className="muted small"
              style={{ display: 'block', fontSize: 12, color: 'var(--muted)' }}
            >
              AI 研发流程平台 · 需求启程,一路旗程:需求 → 开发 → 测试 → 发布 → 归档
            </span>
          </span>
        </div>

        {/* 登录卡片 */}
        <div className="login-box">
          <div>
            <h2 style={{ fontSize: 17, marginBottom: 4 }}>登录</h2>
            <div className="muted small" style={{ color: 'var(--muted)', fontSize: 12 }}>
              手机号 + 密码登录(JWT · access 2h · 短信验证码 V2)
            </div>
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

          {/* 徽章 */}
          <div className="chip-row small" style={{ justifyContent: 'center' }}>
            <span className="bdg b-green">
              <Key className="w-3 h-3" />
              GitLab token 已绑定(luowen@gitlab.internal)
            </span>
          </div>
        </div>

        {/* 底部演示账号说明 */}
        <div
          className="small muted"
          style={{
            textAlign: 'center',
            fontSize: 12,
            color: 'var(--muted)',
            marginTop: 12,
          }}
        >
          演示账号:罗文(超管)/ 王倩(产品)/ 李明(测试)/ 张野(只读);注册为邀请制(token 由超管在「用户管理」生成)
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
