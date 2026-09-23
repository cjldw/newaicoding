/**
 * Dashboard 占位页 — /
 * R21 才实现完整工作台, 当前仅显示标题
 * 作为 MainLayout 的子路由渲染
 */

import { LayoutDashboard } from 'lucide-react'
import { Card } from '@/components/ui/Card'

export function Dashboard() {
  return (
    <div className="px-4 py-6">
      <div className="max-w-4xl mx-auto">
        {/* R2.F8(BUG-UI-068):占位页补 icon(注:router 实挂 pages/dashboard/Dashboard.tsx,本文件为遗留占位) */}
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-text mb-6"><LayoutDashboard size={18} /> 工作台</h1>
        <Card className="p-12 text-center">
          <p className="text-text-muted">
            工作台功能将在 R21 迭代中实现
          </p>
        </Card>
      </div>
    </div>
  )
}
