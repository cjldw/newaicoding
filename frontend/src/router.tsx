/**
 * 路由配置 — react-router-dom v6
 * - /login → 登录页
 * - /register → 注册页
 * - /forgot-password → 找回密码(V2 占位)
 * - /reset-password → 重置密码(V2 占位)
 * - /settings → 设置页布局(左侧导航 + 右侧内容区)
 *   - /settings/profile → 个人资料设置
 *   - /settings/gitlab-token → GitLab token 设置
 * - / (MainLayout) → 工作台 / 项目 / 平台设置(superadmin)
 * - /admin/platform-settings → 平台设置(superadmin)
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
import { MainLayout } from '@/components/layout/MainLayout'
import { ProjectList } from '@/pages/projects/ProjectList'
import { ProjectCreate } from '@/pages/projects/ProjectCreate'
import { ProjectDetail } from '@/pages/projects/ProjectDetail'
import { PlatformSettings } from '@/pages/admin/PlatformSettings'
import { SkillsMarket } from '@/pages/admin/SkillsMarket'
import { RunnerManagement } from '@/pages/admin/RunnerManagement'
import { RequirementList } from '@/pages/requirements/RequirementList'
import { RequirementDetail } from '@/pages/requirements/RequirementDetail'

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
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'projects', element: <ProjectList /> },
      { path: 'projects/create', element: <ProjectCreate /> },
      { path: 'projects/:projectId', element: <ProjectDetail /> },
      { path: 'projects/:projectId/requirements', element: <RequirementList /> },
      { path: 'requirements/:reqId', element: <RequirementDetail /> },
    ],
  },
  { path: '/admin/platform-settings', element: <PlatformSettings /> },
  { path: '/admin/skills', element: <SkillsMarket /> },
  { path: '/admin/runners', element: <RunnerManagement /> },
  { path: '*', element: <Navigate to="/" replace /> },
])
