/**
 * SkillsManagement — Skills 管理 Tab(R17;R4 市场搜索安装;R6 系统级只读 Tab)
 * - 标题"Skills 管理" + "从市场安装"(secondary) + "上传自定义"(primary)按钮(viewer 隐藏)
 * - 已安装 Table:Skill 名/描述/来源徽章(platform=secondary/project=primary)/安装人/安装时间/操作[查看/卸载]
 * - 市场安装对话框:三 Tab「市场安装(R1 源 Select+防抖搜索+远程安装) | 平台库(原平铺列表) | 系统级(R6 镜像内置只读)」
 * - 上传对话框 + Skill 详情对话框
 */

import { useState } from 'react'
import { Upload, Store, Eye, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Alert } from '@/components/ui/Alert'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useInstalledSkills, useSkillMarket, useInstallSkill, useUploadSkill,
  useUninstallSkill, useMarketSources, useMarketSearch, useInstallRemote,
  useSystemAssets, getSkillErrorMessage,
} from '@/api/skills'
import type { Skill, MarketSearchItem } from '@/api/skills'
import { ApiError } from '@/api/client'
import { useDebounce } from '@/hooks/useDebounce'
import { useAuthStore } from '@/stores/authStore'
import { useProjectMembers } from '@/api/projects'

interface SkillsManagementProps {
  projectId: string
}

/** 市场搜索/远程安装失败文案(R2/R3:17005=市场暂不可用;其余照 Skill 错误码) */
function getMarketErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === 17005) return '市场暂不可用'
  return getSkillErrorMessage(error)
}

export function SkillsManagement({ projectId }: SkillsManagementProps) {
  const { data: installed, isLoading } = useInstalledSkills(projectId)
  const { data: marketSkills } = useSkillMarket()
  const installSkill = useInstallSkill(projectId)
  const uploadSkill = useUploadSkill(projectId)
  const uninstallSkill = useUninstallSkill(projectId)
  // ---- R4:市场搜索安装(Dialog 双 Tab)----
  const [marketOpen, setMarketOpen] = useState(false)
  // R6:'system' 第三 Tab(镜像内置 skills 只读,无写入口)
  type MarketTab = 'market' | 'library' | 'system'
  const [marketTab, setMarketTab] = useState<MarketTab>('market')
  const [searchInput, setSearchInput] = useState('')
  const searchQ = useDebounce(searchInput.trim(), 300)
  const [marketType, setMarketType] = useState('')
  const [remoteInstalled, setRemoteInstalled] = useState<Set<string>>(new Set())
  // R4:市场源(R1 裸数组)+ 防抖搜索 + 远程安装
  const { data: marketSources } = useMarketSources()
  const activeMarket = marketType || marketSources?.[0]?.type || ''
  const searchEnabled = marketOpen && marketTab === 'market' && activeMarket !== '' && searchQ !== ''
  const marketSearch = useMarketSearch(activeMarket, searchQ, searchEnabled)
  const installRemote = useInstallRemote(projectId)
  // R6:系统级资产快照(镜像内置,只读;未采集 → 引导态「暂未采集」)
  const { data: systemAssets } = useSystemAssets()
  // 已装比对(R4:命中 installed 列表 name 即禁按;本会话刚装的 ref 兜底,防列表刷新竞态)
  const installedNames = new Set((installed ?? []).map(s => s.name))
  const sourceOptions = (marketSources ?? []).map(s => ({ label: s.name, value: s.type }))
  const { data: membersData } = useProjectMembers(projectId)
  const user = useAuthStore(state => state.user)
  const currentMember = membersData?.items.find(m => m.user_id === user?.user_id)
  const isViewer = currentMember?.role === 'viewer'

  const [uploadOpen, setUploadOpen] = useState(false)
  const [detailSkill, setDetailSkill] = useState<Skill | null>(null)
  const [uninstallTarget, setUninstallTarget] = useState<Skill | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function handleInstall(skillId: string) {
    installSkill.mutate(skillId, {
      onSuccess: () => {
        setMessage({ type: 'success', text: '安装成功' })
        setMarketOpen(false)
      },
      onError: (err) => setMessage({ type: 'error', text: getSkillErrorMessage(err) }),
    })
  }

  /** R4:市场远程安装成功——Dialog 不关,该行标「已安装」+ 刷新已装列表 */
  function handleInstallRemote(item: MarketSearchItem) {
    installRemote.mutate({ market: item.market, ref: item.ref }, {
      onSuccess: (data) => {
        setRemoteInstalled(prev => new Set(prev).add(`${item.market}:${item.ref}`))
        setMessage({
          type: 'success',
          text: data.extra_files > 1
            ? `安装成功,需新启任务容器生效;含 ${data.extra_files} 个支撑文件,仅安装 SKILL.md`
            : '安装成功,需新启任务容器生效',
        })
      },
      onError: (err) => setMessage({ type: 'error', text: getMarketErrorMessage(err) }),
    })
  }

  function handleUpload() {
    if (!selectedFile) return
    uploadSkill.mutate(selectedFile, {
      onSuccess: () => {
        setMessage({ type: 'success', text: '上传成功' })
        setUploadOpen(false)
        setSelectedFile(null)
      },
      onError: (err) => setMessage({ type: 'error', text: getSkillErrorMessage(err) }),
    })
  }

  function handleUninstall() {
    if (!uninstallTarget) return
    uninstallSkill.mutate(uninstallTarget.skill_id, {
      onSuccess: () => {
        setMessage({ type: 'success', text: '卸载成功' })
        setUninstallTarget(null)
      },
      onError: (err) => setMessage({ type: 'error', text: getSkillErrorMessage(err) }),
    })
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  function formatDate(dateStr: string): string {
    try {
      return new Date(dateStr).toLocaleString('zh-CN')
    } catch {
      return dateStr
    }
  }

  return (
    <div>
      {/* 页头 */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><Store size={18} /> Skills 管理</h1>
          <div className="sub">项目已安装的 Skills:查看、卸载与新增</div>
        </div>
        {!isViewer && (
          <div className="acts">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setMessage(null)
                setMarketTab('market')
                setSearchInput('')
                setMarketType('')
                setRemoteInstalled(new Set())
                setMarketOpen(true)
              }}
            >
              <Store className="w-4 h-4 mr-1" />
              从市场安装
            </Button>
            <Button size="sm" onClick={() => setUploadOpen(true)}>
              <Upload className="w-4 h-4 mr-1" />
              上传自定义
            </Button>
          </div>
        )}
      </div>

      {/* 已安装列表 */}
      {isLoading ? (
        <div className="text-text-muted py-8">加载中...</div>
      ) : (
        <div className="card">
        <div className="scrollx">
        <Table className="tbl">
          <TableHeader>
            <TableRow>
              <TableHead>Skill 名</TableHead>
              <TableHead>描述</TableHead>
              <TableHead>来源</TableHead>
              <TableHead>安装人</TableHead>
              <TableHead>安装时间</TableHead>
              <TableHead className="w-[150px]">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(installed ?? []).map(skill => (
              <TableRow key={skill.skill_id}>
                <TableCell className="font-medium text-text">{skill.name}</TableCell>
                <TableCell className="text-text-muted">{skill.description}</TableCell>
                <TableCell>
                  <Badge variant={skill.scope === 'platform' ? 'secondary' : 'default'}>
                    {skill.scope === 'platform' ? '平台' : '项目'}
                  </Badge>
                </TableCell>
                <TableCell className="text-text-muted">
                  {skill.installed_by?.username ?? '-'}
                </TableCell>
                <TableCell className="text-text-muted">
                  {skill.installed_at ? formatDate(skill.installed_at) : '-'}
                </TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setDetailSkill(skill)}>
                      <Eye className="w-4 h-4 mr-1" />
                      查看
                    </Button>
                    {!isViewer && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setUninstallTarget(skill)}
                        className="text-red-fg hover:text-red-fg"
                      >
                        <Trash2 className="w-4 h-4 mr-1" />
                        卸载
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {(installed ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-text-muted py-8">
                  暂无已安装的 Skills
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </div>
        </div>
      )}

      {message && (
        <Alert variant={message.type === 'success' ? 'success' : 'error'}>
          {message.text}
        </Alert>
      )}

      {/* 市场安装对话框(R4:市场搜索安装 + 平台库 双 Tab) */}
      <Dialog open={marketOpen} onOpenChange={setMarketOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>从市场安装</DialogTitle>
            <DialogDescription>
              从市场搜索或从平台库选择 Skill 安装到本项目;「系统级」为镜像内置只读列表
            </DialogDescription>
          </DialogHeader>
          <div className="tabs">
            <button
              className={`tab${marketTab === 'market' ? ' on' : ''}`}
              onClick={() => setMarketTab('market')}
            >
              市场安装
            </button>
            <button
              className={`tab${marketTab === 'library' ? ' on' : ''}`}
              onClick={() => setMarketTab('library')}
            >
              平台库
            </button>
            <button
              className={`tab${marketTab === 'system' ? ' on' : ''}`}
              onClick={() => setMarketTab('system')}
            >
              系统级
            </button>
          </div>
          {message && (
            <div className="mt-3">
              <Alert variant={message.type === 'success' ? 'success' : 'error'}>
                {message.text}
              </Alert>
            </div>
          )}
          {marketTab === 'market' ? (
            <div className="mt-3 space-y-3">
              {/* 市场源(R1)+ 搜索词(300ms 防抖) */}
              <div className="flex gap-2">
                <Select
                  className="w-[150px] flex-none"
                  options={sourceOptions}
                  value={activeMarket}
                  onChange={(e) => setMarketType(e.target.value)}
                />
                <Input
                  className="flex-1"
                  placeholder="搜索市场 skill…"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                />
              </div>
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {searchQ === '' ? (
                  <p className="text-center text-text-muted py-4">请输入搜索词</p>
                ) : marketSearch.isLoading ? (
                  <p className="text-center text-text-muted py-4">搜索中...</p>
                ) : marketSearch.isError ? (
                  <Alert variant="error">{getMarketErrorMessage(marketSearch.error)}</Alert>
                ) : (marketSearch.data?.items ?? []).length === 0 ? (
                  <p className="text-center text-text-muted py-4">未找到匹配 skill</p>
                ) : (
                  (marketSearch.data?.items ?? []).map(item => {
                    const installedItem =
                      installedNames.has(item.name) ||
                      remoteInstalled.has(`${item.market}:${item.ref}`)
                    return (
                      <div
                        key={`${item.market}:${item.ref}`}
                        className="flex items-center justify-between p-3 border border-border rounded-md"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-text">{item.name}</span>
                            <span className="bdg b-zinc">{item.installs} 次安装</span>
                          </div>
                          <div className="text-sm text-text-muted mt-1 truncate">
                            {item.description}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          className="ml-3 flex-none"
                          onClick={() => handleInstallRemote(item)}
                          disabled={installedItem || installRemote.isPending}
                        >
                          {installedItem ? '已安装' : '安装'}
                        </Button>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          ) : marketTab === 'library' ? (
            <div className="mt-3 space-y-2 max-h-[400px] overflow-y-auto">
              {(marketSkills ?? []).map(skill => (
                <div
                  key={skill.skill_id}
                  className="flex items-center justify-between p-3 border border-border rounded-md"
                >
                  <div className="flex-1">
                    <div className="font-medium text-text">{skill.name}</div>
                    <div className="text-sm text-text-muted mt-1">{skill.description}</div>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => handleInstall(skill.skill_id)}
                    disabled={installSkill.isPending}
                  >
                    安装
                  </Button>
                </div>
              ))}
              {(marketSkills ?? []).length === 0 && (
                <p className="text-center text-text-muted py-4">暂无可安装的 Skills</p>
              )}
            </div>
          ) : (
            /* R6:系统级 Tab(镜像内置 skills 只读列表,无安装/卸载入口) */
            <div className="mt-3 space-y-2 max-h-[400px] overflow-y-auto">
              {systemAssets?.collected ? (
                <>
                  {systemAssets.collected_at && (
                    <p className="text-sm text-text-muted">
                      采集于 {formatDate(systemAssets.collected_at)}
                    </p>
                  )}
                  {(systemAssets.skills ?? []).map(s => (
                    <div
                      key={s.name}
                      className="flex items-center justify-between p-3 border border-border rounded-md"
                    >
                      <span className="font-medium text-text">{s.name}</span>
                      <span className="bdg b-zinc">镜像内置</span>
                    </div>
                  ))}
                  {(systemAssets.skills ?? []).length === 0 && (
                    <p className="text-center text-text-muted py-4">镜像未内置 Skills</p>
                  )}
                </>
              ) : (
                <p className="text-center text-text-muted py-4">暂未采集</p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* 上传自定义对话框 */}
      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>上传自定义 Skill</DialogTitle>
            <DialogDescription>上传 .md 文件,需包含 YAML frontmatter(name/description)</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <input
              type="file"
              accept=".md"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-text-muted file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-primary/10 file:text-primary hover:file:bg-primary/20"
            />
            {selectedFile && (
              <p className="text-sm text-text-muted">
                已选择: {selectedFile.name} ({formatFileSize(selectedFile.size)})
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUploadOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={handleUpload}
              disabled={!selectedFile || uploadSkill.isPending}
            >
              上传
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Skill 详情对话框 */}
      <Dialog open={!!detailSkill} onOpenChange={(open) => !open && setDetailSkill(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Skill 详情</DialogTitle>
            <DialogDescription>{detailSkill?.name}</DialogDescription>
          </DialogHeader>
          <pre className="font-mono text-xs bg-surface-strong p-4 rounded-md overflow-auto max-h-[400px]">
            {detailSkill?.content ?? '无内容'}
          </pre>
        </DialogContent>
      </Dialog>

      {/* 卸载确认对话框 */}
      <Dialog open={!!uninstallTarget} onOpenChange={(open) => !open && setUninstallTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认卸载</DialogTitle>
            <DialogDescription>
              确定要卸载 Skill "{uninstallTarget?.name}" 吗?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUninstallTarget(null)}>
              取消
            </Button>
            <Button
              variant="danger"
              onClick={handleUninstall}
              disabled={uninstallSkill.isPending}
            >
              卸载
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
