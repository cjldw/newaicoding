/**
 * Dialog — shadcn/ui New York 风格手写组件
 * 遮罩层 + 居中浮层,淡入淡出 + 缩放动画
 */

import * as React from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

// ---- Portal ----
interface PortalProps {
  children: React.ReactNode
}

function PortalContainer({ children }: PortalProps) {
  const [container, setContainer] = React.useState<HTMLElement | null>(null)

  React.useEffect(() => {
    let el = document.getElementById('dialog-portal')
    if (!el) {
      el = document.createElement('div')
      el.id = 'dialog-portal'
      document.body.appendChild(el)
    }
    setContainer(el)
  }, [])

  if (!container) return null
  return createPortal(children, container)
}

// ---- Overlay ----
interface DialogOverlayProps extends React.HTMLAttributes<HTMLDivElement> {}

const DialogOverlay = React.forwardRef<HTMLDivElement, DialogOverlayProps>(
  ({ className = '', ...props }, ref) => (
    <div
      ref={ref}
      className="fixed inset-0 z-50 bg-black/50 animate-in fade-in-0"
      style={{
        animation: 'dialogOverlayIn 150ms ease-out',
      }}
      {...props}
    />
  ),
)
DialogOverlay.displayName = 'DialogOverlay'

// ---- Content ----
interface DialogContentProps extends React.HTMLAttributes<HTMLDivElement> {
  onClose?: () => void
  showClose?: boolean
}

const DialogContent = React.forwardRef<HTMLDivElement, DialogContentProps>(
  ({ className = '', children, onClose, showClose = true, ...props }, ref) => (
    <PortalContainer>
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <DialogOverlay onClick={onClose} />
        <div
          ref={ref}
          role="dialog"
          aria-modal="true"
          className={`relative z-50 w-[500px] max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-surface p-6 shadow-lg ${className}`}
          style={{
            animation: 'dialogContentIn 150ms ease-out',
          }}
          onClick={(e) => e.stopPropagation()}
          {...props}
        >
          {children}
          {showClose && onClose && (
            <button
              type="button"
              className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
              <span className="sr-only">关闭</span>
            </button>
          )}
        </div>
      </div>
    </PortalContainer>
  ),
)
DialogContent.displayName = 'DialogContent'

// ---- Header ----
interface DialogHeaderProps extends React.HTMLAttributes<HTMLDivElement> {}

function DialogHeader({ className = '', ...props }: DialogHeaderProps) {
  return (
    <div
      className={`flex flex-col space-y-1.5 text-center sm:text-left ${className}`}
      {...props}
    />
  )
}

// ---- Footer ----
interface DialogFooterProps extends React.HTMLAttributes<HTMLDivElement> {}

function DialogFooter({ className = '', ...props }: DialogFooterProps) {
  return (
    <div
      className={`flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 ${className}`}
      {...props}
    />
  )
}

// ---- Title ----
interface DialogTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {}

const DialogTitle = React.forwardRef<HTMLHeadingElement, DialogTitleProps>(
  ({ className = '', ...props }, ref) => (
    <h2
      ref={ref}
      className={`text-lg font-semibold leading-none tracking-tight text-text ${className}`}
      {...props}
    />
  ),
)
DialogTitle.displayName = 'DialogTitle'

// ---- Description ----
interface DialogDescriptionProps extends React.HTMLAttributes<HTMLParagraphElement> {}

const DialogDescription = React.forwardRef<HTMLParagraphElement, DialogDescriptionProps>(
  ({ className = '', ...props }, ref) => (
    <p
      ref={ref}
      className={`text-sm text-text-muted ${className}`}
      {...props}
    />
  ),
)
DialogDescription.displayName = 'DialogDescription'

// ---- Root (context provider for open/close) ----
interface DialogProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}

function Dialog({ open = false, onOpenChange, children }: DialogProps) {
  // Close on Escape
  React.useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onOpenChange?.(false)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onOpenChange])

  // Lock body scroll when open
  React.useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  if (!open) return null

  // Clone children to inject onClose
  const childrenWithClose = React.Children.map(children, (child) => {
    if (React.isValidElement(child) && child.type === DialogContent) {
      return React.cloneElement(child as React.ReactElement<DialogContentProps>, {
        onClose: () => onOpenChange?.(false),
      })
    }
    return child
  })

  return <>{childrenWithClose}</>
}

export {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}
