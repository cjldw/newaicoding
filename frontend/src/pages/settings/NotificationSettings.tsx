/**
 * 通知设置页 /settings/notifications
 * - 个人资料设置的一部分(第三项)
 * - 钉钉 webhook 配置 + 通知渠道开关 + 测试发送按钮
 */

import { useState, useEffect } from 'react'
import { Bell, Send, Loader2, Save } from 'lucide-react'
import {
  useNotificationSettings, useUpdateNotificationSettings, useTestDingtalk,
} from '@/api/notifications'
import { useToast } from '@/hooks/useToast'

export function NotificationSettings() {
  const [, showToast, ToastEl] = useToast()
  const { data, isLoading } = useNotificationSettings()
  const updateSettings = useUpdateNotificationSettings()
  const testDingtalk = useTestDingtalk()

  // 本地表单状态(从后端数据初始化)
  const [webhook, setWebhook] = useState('')
  const [dingtalkEnabled, setDingtalkEnabled] = useState(false)
  const [realtimeToast, setRealtimeToast] = useState(false)
  const [dirty, setDirty] = useState(false)

  // 后端数据加载后同步到本地状态
  useEffect(() => {
    if (data) {
      setWebhook(data.dingtalk_webhook ?? '')
      setDingtalkEnabled(data.dingtalk_enabled)
      setRealtimeToast(data.realtime_toast_enabled)
      setDirty(false)
    }
  }, [data])

  // 任意字段变更 → 标记 dirty
  function markDirty() {
    setDirty(true)
  }

  async function handleSave() {
    try {
      await updateSettings.mutateAsync({
        dingtalk_webhook: webhook.trim() || undefined,
        dingtalk_enabled: dingtalkEnabled,
        realtime_toast_enabled: realtimeToast,
      })
      showToast('ok', '保存成功')
      setDirty(false)
    } catch {
      showToast('err', '保存失败')
    }
  }

  async function handleTest() {
    if (!webhook.trim()) {
      showToast('err', '请先填写钉钉 Webhook 地址')
      return
    }
    try {
      const res = await testDingtalk.mutateAsync({
        dingtalk_webhook: webhook.trim(),
        dingtalk_enabled: true,
      })
      showToast('ok', res?.message ?? '测试消息已发送')
    } catch {
      showToast('err', '测试发送失败')
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={20} className="animate-spin" />
        <span className="ml-2 text-sm text-text-muted">加载中…</span>
      </div>
    )
  }

  return (
    <div>
      {/* R2.F8(BUG-UI-068):统一 page-head + h1 + icon 惯例(原 icon 行升格) */}
      <div className="page-head">
        <h1 className="flex items-center gap-2"><Bell size={18} /> 通知设置</h1>
      </div>

      {/* 钉钉通知 */}
      <div className="bg-surface border border-border rounded-lg p-5 mb-5">
        <h3 className="text-sm font-medium mb-4">钉钉机器人通知</h3>

        <div className="mb-4">
          <label className="block text-sm text-text-muted mb-1.5">
            Webhook 地址
          </label>
          <input
            type="url"
            className="w-full px-3 py-2 bg-bg border border-border rounded-md text-sm outline-none focus:border-primary transition-colors"
            placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
            value={webhook}
            onChange={(e) => { setWebhook(e.target.value); markDirty() }}
          />
          <p className="text-xs text-text-muted mt-1">
            在钉钉群中添加「自定义机器人」,复制 Webhook 地址粘贴到此处
          </p>
        </div>

        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm font-medium">启用钉钉通知</div>
            <div className="text-xs text-text-muted">部署失败、Runner 离线等关键事件推送到钉钉群</div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={dingtalkEnabled}
              onChange={(e) => { setDingtalkEnabled(e.target.checked); markDirty() }}
            />
            <div className="w-9 h-5 bg-border rounded-full peer peer-checked:bg-primary transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4" />
          </label>
        </div>

        <button
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs bg-bg border border-border rounded-md hover:bg-surface transition-colors disabled:opacity-50"
          onClick={handleTest}
          disabled={testDingtalk.isPending || !webhook.trim()}
        >
          {testDingtalk.isPending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
          测试发送
        </button>
      </div>

      {/* 站内实时通知 */}
      <div className="bg-surface border border-border rounded-lg p-5 mb-5">
        <h3 className="text-sm font-medium mb-4">站内实时通知</h3>

        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Toast 弹窗提醒</div>
            <div className="text-xs text-text-muted">收到通知时在页面右上角弹出提示(需浏览器允许通知)</div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={realtimeToast}
              onChange={(e) => { setRealtimeToast(e.target.checked); markDirty() }}
            />
            <div className="w-9 h-5 bg-border rounded-full peer peer-checked:bg-primary transition-colors after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4" />
          </label>
        </div>
      </div>

      {/* 保存按钮 */}
      <div className="flex justify-end">
        <button
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary text-white text-sm font-medium rounded-md hover:opacity-90 transition-opacity disabled:opacity-50"
          onClick={handleSave}
          disabled={updateSettings.isPending || !dirty}
        >
          {updateSettings.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          保存设置
        </button>
      </div>

      {ToastEl}
    </div>
  )
}
