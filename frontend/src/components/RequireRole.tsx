/**
 * RequireRole — 角色守卫组件(R19 BUG-003)
 * - 等待 hydrate 完成(token 存在但 user 为 null 时)
 * - 校验 user.role === requiredRole
 * - 不满足则重定向到 /
 */

import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

interface RequireRoleProps {
  requiredRole: string
  children: React.ReactNode
}

export function RequireRole({ requiredRole, children }: RequireRoleProps) {
  const location = useLocation()
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)

  // 无 token → 未登录,跳转登录页
  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // token 存在但 user 为 null → hydrate 中,显示加载
  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-text-muted">加载中...</div>
      </div>
    )
  }

  // user 已恢复,校验角色
  if (user.role !== requiredRole) {
    // 非超管访问超管路由 → 重定向到首页
    return <Navigate to="/" replace />
  }

  // 角色匹配,渲染子组件
  return <>{children}</>
}
