import * as React from 'react'

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'success' | 'error' | 'warning' | 'primary' | 'secondary' | 'outline'
}

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className = '', variant = 'default', ...props }, ref) => {
    const variantClasses: Record<string, string> = {
      default: 'bg-surface-strong border-border text-text-muted',
      success: 'bg-green-100 border-green-200 text-green-800',
      error: 'bg-red-100 border-red-200 text-red-800',
      warning: 'bg-yellow-100 border-yellow-200 text-yellow-800',
      // R2: 角色徽章变体
      primary: 'bg-primary/10 border-primary/20 text-primary',
      secondary: 'bg-accent/10 border-accent/20 text-accent',
      outline: 'bg-transparent border-border text-text-muted',
    }

    return (
      <span
        ref={ref}
        className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${variantClasses[variant]} ${className}`}
        {...props}
      />
    )
  }
)
Badge.displayName = 'Badge'

export { Badge }
