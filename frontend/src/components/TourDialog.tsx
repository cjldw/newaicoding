/**
 * TourDialog — R29 平台导览弹窗
 * - 复用 ui/Dialog(shadcn New York:遮罩 rgba(0,0,0,.5)=分片规格、p-6=24px、shadow-lg、Esc 关闭、body 滚动锁)
 * - 宽 480px / 圆角 0.5rem / 出现动效(translateY 10px→0, 0.3s ease-out)按分片以 inline style 覆盖默认值
 * - 编号步骤列表(1-N 动态生成,条件步骤按用户数据显隐,来源 useTourSteps)
 * - 步骤点击:关闭弹窗 + 跳转(不写标记,与分片控件联动一致)
 * - 完成/跳过:写 localStorage tour_completed="true" → 关闭,后续不再自动弹出
 * - 遮罩点击:仅关闭,不写标记(下次登录仍自动弹出)
 * - 挂载策略:由 MainLayout 条件渲染(open 时才挂载)→ useTourSteps 仅在弹窗打开时发请求
 *   (BUG-UI-071 方案②:open 状态显式透传给 useTourSteps 的 enabled,查询层再加一道门)
 */
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Play } from 'lucide-react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/Dialog'
import { useTourSteps } from '@/hooks/useTourSteps'

const TOUR_STORAGE_KEY = 'tour_completed'

/** 写完成标记;localStorage 不可用时静默失败(分片错误处理行:不影响本次使用) */
export function markTourCompleted() {
  try {
    localStorage.setItem(TOUR_STORAGE_KEY, 'true')
  } catch {
    /* 静默 */
  }
}

/** 读取完成标记;localStorage 不可用时视为未完成(下次仍自动弹出,可接受) */
export function isTourCompleted(): boolean {
  try {
    return localStorage.getItem(TOUR_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

interface TourDialogProps {
  /** 弹窗开合状态(MainLayout 的 tourOpen):仅 open 时才发起导览数据链请求 */
  open: boolean
  onClose: () => void
}

export function TourDialog({ open, onClose }: TourDialogProps) {
  const navigate = useNavigate()
  const { steps } = useTourSteps({ enabled: open })

  // 点击步骤:关闭弹窗 → 跳转对应页面
  function handleStepClick(link: string) {
    onClose()
    navigate(link)
  }

  // 完成/跳过:写标记 → 关闭
  function handleFinish() {
    markTourCompleted()
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent
        showClose={false}
        className="tour-dialog"
        style={{ width: 480, borderRadius: '0.5rem', animation: 'tourIn 0.3s ease-out' }}
      >
        {/* R33:标题补图标 + 副标语(原裸标题偏单薄) */}
        <DialogTitle>
          <span className="tour-title-ico"><Play size={15} />平台导览</span>
        </DialogTitle>
        <p className="small muted" style={{ margin: '2px 0 12px' }}>
          按顺序走一遍平台核心页面,约 2 分钟;点击任意步骤直接跳转。
        </p>
        <div className="tour-steps">
          {steps.map((s) => (
            <button
              key={s.n}
              type="button"
              className="tour-step"
              onClick={() => handleStepClick(s.link)}
            >
              <span className="n">{s.n}</span>
              <span className="st">{s.title}</span>
              <ChevronRight size={14} className="arr" />
            </button>
          ))}
        </div>
        <div className="tour-dialog-foot">
          <button className="btn" onClick={handleFinish}>跳过</button>
          <button className="btn btn--primary" onClick={handleFinish}>完成导览</button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
