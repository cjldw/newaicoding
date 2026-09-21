/**
 * 找回密码页 — /forgot-password
 * V2 占位页: 显示 V2 功能提示 + 返回登录链接
 */

import { Link } from 'react-router-dom'
import { ArrowLeft, Info } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Alert } from '@/components/ui/Alert'

export function ForgotPassword() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <Card className="w-full max-w-md p-6">
        {/* 标题 */}
        <div className="flex flex-col items-center mb-8">
          <img src="/logo.svg" alt="Logo" className="w-12 h-12 mb-4" />
          <h1 className="text-xl font-semibold text-text">找回密码</h1>
          <p className="text-sm text-text-muted mt-1">重置您的账号密码</p>
        </div>

        {/* V2 提示 */}
        <Alert variant="warning" className="mb-6">
          <div className="flex items-start gap-2">
            <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium">V2 功能</p>
              <p className="mt-1 text-sm opacity-80">
                找回密码功能将在 V2 版本中开放。当前版本暂不支持自助找回密码，请联系管理员协助处理。
              </p>
            </div>
          </div>
        </Alert>

        {/* 返回登录 */}
        <div className="flex justify-center">
          <Link to="/login" className="text-accent hover:text-text transition-colors flex items-center gap-1 text-sm">
            <ArrowLeft className="w-4 h-4" />
            返回登录
          </Link>
        </div>
      </Card>
    </div>
  )
}
