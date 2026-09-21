import * as React from 'react'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary'
}

/**
 * shadcn/ui New York 风格按钮
 * - 默认: .btn 样式
 * - primary: .btn--primary 样式
 * - 支持 disabled、loading 态
 */
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'default', children, disabled, ...props }, ref) => {
    const baseClass = variant === 'primary' ? 'btn btn--primary' : 'btn'
    return (
      <button
        className={`${baseClass} ${className}`}
        ref={ref}
        disabled={disabled}
        {...props}
      >
        {children}
      </button>
    )
  }
)
Button.displayName = 'Button'

export { Button }
