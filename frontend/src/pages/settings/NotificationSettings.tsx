/**
 * 通知设置页 /settings/notifications
 * - 个人设置第三项:钉钉 webhook 配置 + 通知渠道开关 + 测试发送按钮
 * - 全面回归平台体系:ui/Card、ui/Input、ui/Label、ui/Button(btn/btn-pri),
 *   加载态走 .page-loading(与 Profile/GitLabToken 两页统一)
 */

import { useState, useEffect } from 'react'
import { Bell, Send, Loader2, Save } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Label } from '@/components/ui/Label'
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
      <div className="page-loading">
        <Loader2 className="w-4 h-4 animate-spin" />
        加载中…
      </div>
    )
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><Bell size={18} /> 通知设置</h1>
          <div className="sub">配置钉钉机器人 Webhook 与站内 Toast 提醒 · 部署失败、Runner 离线等关键事件及时触达</div>
        </div>
      </div>

      {/* 钉钉通知 */}
      <Card className="p-6 mb-4">
        <h3 className="text-lg font-medium text-text mb-4">钉钉机器人通知</h3>

        <div className="space-y-2 mb-4">
          <Label htmlFor="dingtalk-webhook">Webhook 地址</Label>
          <Input
            id="dingtalk-webhook"
            type="url"
            placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
            value={webhook}
            onChange={(e) => { setWebhook(e.target.value); markDirty() }}
          />
          <p className="text-xs text-text-muted">
            在钉钉群中添加「自定义机器人」,复制 Webhook 地址粘贴到此处
          </p>
        </div>

        <div className="flex items-center justify-between mb-4">
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

        <Button
          type="button"
          className="gap-2"
          onClick={handleTest}
          disabled={testDingtalk.isPending || !webhook.trim()}
        >
          {testDingtalk.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          测试发送
        </Button>
      </Card>

      {/* 站内实时通知 */}
      <Card className="p-6">
        <h3 className="text-lg font-medium text-text mb-4">站内实时通知</h3>

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
      </Card>

      {/* 保存:右对齐主色按钮(两个分区共用,置于卡片外底部一行) */}
      <div className="flex justify-end" style={{ marginTop: 16 }}>
        <Button
          type="button"
          variant="primary"
          className="gap-2"
          onClick={handleSave}
          disabled={updateSettings.isPending || !dirty}
        >
          {updateSettings.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          保存设置
        </Button>
      </div>

      {ToastEl}
    </div>
  )
}
