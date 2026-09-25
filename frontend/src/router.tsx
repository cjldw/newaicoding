/**
 * 路由配置 — react-router-dom v6
 * - /login → 登录页
 * - /register → 注册页
 * - /forgot-password → 找回密码(V2 占位)
 * - /reset-password → 重置密码(V2 占位)
 * - / (MainLayout) → 工作台 / 项目 / 设置 / 平台设置(superadmin)
 *   - /settings → 设置布局(嵌套于 MainLayout:全局侧栏/面包屑保留 + 左导航 + 右内容)
 *     - /settings/profile → 个人资料设置
 *     - /settings/gitlab-token → GitLab token 设置
 *     - /settings/notifications → 通知设置
 * - /admin/platform-settings → 平台设置(superadmin)
 */

import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Login } from '@/pages/auth/Login'
import { Register } from '@/pages/auth/Register'
import { ForgotPassword } from '@/pages/auth/ForgotPassword'
import { ResetPassword } from '@/pages/auth/ResetPassword'
import { ProfileSettings } from '@/pages/settings/ProfileSettings'
import { GitLabTokenSettings } from '@/pages/settings/GitLabTokenSettings'
import { NotificationSettings } from '@/pages/settings/NotificationSettings'
import { Dashboard } from '@/pages/dashboard/Dashboard'
import { SettingsLayout } from '@/components/layout/SettingsLayout'
import { MainLayout } from '@/components/layout/MainLayout'
import { ProjectList } from '@/pages/projects/ProjectList'
import { ProjectCreate } from '@/pages/projects/ProjectCreate'
import { ProjectDetail } from '@/pages/projects/ProjectDetail'
import { PlatformSettings } from '@/pages/admin/PlatformSettings'
import { SkillsMarket } from '@/pages/admin/SkillsMarket'
import { RunnerManagement } from '@/pages/admin/RunnerManagement'
import UserManagementPage from '@/pages/admin/UserManagementPage'
import AuditLogsPage from '@/pages/admin/AuditLogsPage'
import { RequirementList } from '@/pages/requirements/RequirementList'
import { RequirementDetail } from '@/pages/requirements/RequirementDetail'
import TaskDetail from '@/pages/tasks/TaskDetail'
import TestCasesReview from '@/pages/tasks/TestCasesReview'
import TestReport from '@/pages/tasks/TestReport'
import ArchivePage from '@/pages/requirements/ArchivePage'
import KnowledgeBase from '@/pages/knowledge/KnowledgeBase'
import KnowledgeBaseList from '@/pages/knowledge/KnowledgeBaseList'
import KnowledgeBaseView from '@/pages/knowledge/KnowledgeBaseView'
import EntryDetail from '@/pages/knowledge/EntryDetail'
import { NotificationCenter } from '@/pages/notifications/NotificationCenter'
import { RequirementsManage, TasksManage, TestsManage, ReleasesManage } from '@/pages/manage/ManagePages'
import { RequireRole } from '@/components/RequireRole'

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  { path: '/register', element: <Register /> },
  { path: '/forgot-password', element: <ForgotPassword /> },
  { path: '/reset-password', element: <ResetPassword /> },
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'notifications', element: <NotificationCenter /> },
      { path: 'projects', element: <ProjectList /> },
      { path: 'projects/create', element: <ProjectCreate /> },
      { path: 'projects/:projectId', element: <ProjectDetail /> },
      { path: 'projects/:projectId/requirements', element: <RequirementList /> },
      { path: 'requirements/:reqId', element: <RequirementDetail /> },
      { path: 'tasks/:taskId', element: <TaskDetail /> },
      { path: 'tasks/:taskId/cases', element: <TestCasesReview /> },
      { path: 'tasks/:taskId/report', element: <TestReport /> },
      { path: 'requirements/:reqId/archive', element: <ArchivePage /> },
      { path: 'projects/:projectId/knowledge', element: <KnowledgeBase /> },
      // R2:知识条目详情(项目级/平台级双路由共用 EntryDetail)
      { path: 'projects/:projectId/knowledge/:entryId', element: <EntryDetail /> },
      { path: 'knowledge/:entryId', element: <EntryDetail /> },
      { path: 'projects/:projectId/knowledge-bases', element: <KnowledgeBaseList /> },
      { path: 'projects/:projectId/knowledge-bases/:kbId', element: <KnowledgeBaseView /> },
      { path: 'knowledge', element: <KnowledgeBase /> },
      { path: 'manage/requirements', element: <RequirementsManage /> },
      { path: 'manage/tasks', element: <TasksManage /> },
      { path: 'manage/tests', element: <TestsManage /> },
      { path: 'manage/releases', element: <ReleasesManage /> },
      // 设置路由 — 挂入 MainLayout 子路由(原顶层独立壳,进设置后脱离全局导航):
      // MainLayout(侧栏/面包屑) > SettingsLayout(左导航) > 具体页,三层嵌套
      {
        path: 'settings',
        element: <SettingsLayout />,
        children: [
          { index: true, element: <Navigate to="profile" replace /> },
          { path: 'profile', element: <ProfileSettings /> },
          { path: 'gitlab-token', element: <GitLabTokenSettings /> },
          { path: 'notifications', element: <NotificationSettings /> },
        ],
      },
      // Admin routes — BUG-004: 移入 MainLayout 子路由;BUG-003: RequireRole 守卫
      {
        path: 'admin/platform-settings',
        element: (
          <RequireRole requiredRole="superadmin">
            <PlatformSettings />
          </RequireRole>
        ),
      },
      {
        path: 'admin/skills',
        element: (
          <RequireRole requiredRole="superadmin">
            <SkillsMarket />
          </RequireRole>
        ),
      },
      {
        path: 'admin/runners',
        element: (
          <RequireRole requiredRole="superadmin">
            <RunnerManagement />
          </RequireRole>
        ),
      },
      {
        path: 'admin/users',
        element: (
          <RequireRole requiredRole="superadmin">
            <UserManagementPage />
          </RequireRole>
        ),
      },
      {
        path: 'admin/audit-logs',
        element: (
          <RequireRole requiredRole="superadmin">
            <AuditLogsPage />
          </RequireRole>
        ),
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
