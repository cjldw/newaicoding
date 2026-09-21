import * as React from 'react'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'ghost' | 'outline'
  size?: 'default' | 'sm' | 'lg'
}

/**
 * shadcn/ui New York 风格按钮
 * - 默认: .btn 样式
 * - primary: .btn--primary 样式
 * - 支持 disabled、loading 态
 */
const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'default', size = 'default', children, disabled, ...props }, ref) => {
    const variantClass =
      variant === 'primary' ? 'btn btn--primary'
      : variant === 'ghost' ? 'btn btn--ghost'
      : variant === 'outline' ? 'btn btn--outline'
      : 'btn'
    const sizeClass =
      size === 'sm' ? 'btn--sm'
      : size === 'lg' ? 'btn--lg'
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
