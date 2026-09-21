/**
 * 路由配置 — react-router-dom v6
 * - /login → 登录页
 * - /register → 注册页
 * - /forgot-password → 找回密码(V2 占位)
 * - /reset-password → 重置密码(V2 占位)
 * - /settings → 设置页布局(左侧导航 + 右侧内容区)
 *   - /settings/profile → 个人资料设置
 *   - /settings/gitlab-token → GitLab token 设置
 * - / → Dashboard(R21 占位)
 */

import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Login } from '@/pages/auth/Login'
import { Register } from '@/pages/auth/Register'
import { ForgotPassword } from '@/pages/auth/ForgotPassword'
import { ResetPassword } from '@/pages/auth/ResetPassword'
import { ProfileSettings } from '@/pages/settings/ProfileSettings'
import { GitLabTokenSettings } from '@/pages/settings/GitLabTokenSettings'
import { Dashboard } from '@/pages/Dashboard'
import { SettingsLayout } from '@/components/layout/SettingsLayout'

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  { path: '/register', element: <Register /> },
  { path: '/forgot-password', element: <ForgotPassword /> },
  { path: '/reset-password', element: <ResetPassword /> },
  {
    path: '/settings',
    element: <SettingsLayout />,
    children: [
      { index: true, element: <Navigate to="profile" replace /> },
      { path: 'profile', element: <ProfileSettings /> },
      { path: 'gitlab-token', element: <GitLabTokenSettings /> },
    ],
  },
  { path: '/', element: <Dashboard /> },
  { path: '*', element: <Navigate to="/" replace /> },
])
