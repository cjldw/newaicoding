import * as React from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'success' | 'error' | 'warning'
  onClose?: () => void
}

/**
 * shadcn/ui New York 风格提示框
 * - 支持 default/success/error/warning 变体
 * - 可选关闭按钮
 * - 3s 自动消失由调用方控制(onClose 回调)
 */
const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  ({ className = '', variant = 'default', children, onClose, ...props }, ref) => {
    const variantClasses: Record<string, string> = {
      default: 'bg-surface-strong border-border text-text',
      success: 'bg-green-50 border-green-200 text-green-800',
      error: 'bg-red-50 border-red-200 text-red-800',
      warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
    }

    const icons: Record<string, React.ReactNode> = {
      default: <Info className="w-4 h-4" />,
      success: <CheckCircle2 className="w-4 h-4" />,
      error: <AlertCircle className="w-4 h-4" />,
      warning: <AlertCircle className="w-4 h-4" />,
    }

    return (
      <div
        ref={ref}
        className={`flex items-start gap-3 p-4 rounded-lg border text-sm ${variantClasses[variant]} ${className}`}
        role="alert"
        {...props}
      >
        <span className="flex-shrink-0 mt-0.5">{icons[variant]}</span>
        <div className="flex-1">{children}</div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="flex-shrink-0 mt-0.5 text-current opacity-60 hover:opacity-100 transition-opacity"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    )
  }
)
Alert.displayName = 'Alert'

export { Alert }
