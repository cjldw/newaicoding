/**
 * Dashboard 占位页 — /
 * R21 才实现完整工作台, 当前仅显示标题
 */

import { Card } from '@/components/ui/Card'

export function Dashboard() {
  return (
    <div className="min-h-screen bg-bg py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-semibold text-text mb-6">工作台</h1>
        <Card className="p-12 text-center">
          <p className="text-text-muted">
            工作台功能将在 R21 迭代中实现
          </p>
        </Card>
      </div>
    </div>
  )
}
