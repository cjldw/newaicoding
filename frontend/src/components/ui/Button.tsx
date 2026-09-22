import * as React from 'react'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'ghost' | 'outline' | 'danger'
  size?: 'default' | 'sm' | 'lg'
}

/**
 * shadcn/ui New York 风格按钮
 * - 默认: .btn 样式
 * - primary: .btn-pri 样式
 * - ghost: .btn-ghost 样式
 * - danger: .btn-danger 样式
 * - 支持 disabled、loading 态
 */
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'default', size = 'default', children, disabled, ...props }, ref) => {
    const variantClass =
      variant === 'primary' ? 'btn btn-pri'
      : variant === 'ghost' ? 'btn btn-ghost'
      : variant === 'danger' ? 'btn btn-danger'
      : variant === 'outline' ? 'btn'
      : 'btn'
    const sizeClass =
      size === 'sm' ? 'btn-sm'
      : size === 'lg' ? ''
      : ''
    return (
      <button
        className={`${variantClass} ${sizeClass} ${className}`.trim()}
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
