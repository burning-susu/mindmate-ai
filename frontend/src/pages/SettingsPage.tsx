import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  CircleAlert,
  Database,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  HardDrive,
  KeyRound,
  LoaderCircle,
  ShieldCheck,
  Trash2,
  Wallet,
  Wifi,
  Cpu,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'

import { ApiError } from '../api/client'
import { BackupRestorePanel } from './BackupRestorePanel'
import {
  createBackup,
  downloadBackup,
  formatBackupSize,
  isBackupInProgress,
  listBackups,
  retryBackup,
  type BackupRecord,
} from '../api/backups'
import {
  acceptExternalAiConsent,
  acceptOpenAiConsent,
  deleteAiProviderKey,
  deleteOpenAiProviderKey,
  getAiProviderStatus,
  saveAiProviderKey,
  saveOpenAiProviderKey,
  setAiGenerationMode,
  testAiProviderConnection,
  testOpenAiProviderConnection,
  type GenerationMode,
} from '../api/aiProvider'
import { getEmbeddingModelStatus } from '../api/knowledgeBases'
import {
  clearDiagnosticLogs,
  downloadDiagnostics,
  formatBytes,
  getAiBudgetStatus,
  getAiUsageSummary,
  getDiagnosticsPreview,
  getPrivacyStatus,
  getStorageOverview,
  updateAiBudget,
} from '../api/systemSettings'

function formatTime(value: string | null | undefined) {
  if (!value) return '尚未测试'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function errorText(error: unknown) {
  if (error instanceof ApiError) return error.problem.detail
  return error instanceof Error ? error.message : '操作失败，请重试。'
}

function Capability({ value }: { value: 'supported' | 'unsupported' | 'unknown' }) {
  const label = value === 'supported' ? '已验证' : value === 'unsupported' ? '不可用' : '未知'
  return <span className={`ai-capability ai-capability--${value}`}>{label}</span>
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="settings-loading">
      <LoaderCircle className="spin" size={18} aria-hidden="true" />
      {label}
    </div>
  )
}

function FailBlock({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <div className="settings-error" role="alert">
      <CircleAlert size={18} aria-hidden="true" />
      <span>{errorText(error)}</span>
      <button className="quiet-button" type="button" onClick={onRetry}>
        重新读取
      </button>
    </div>
  )
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [openAiKey, setOpenAiKey] = useState('')
  const [showOpenAiKey, setShowOpenAiKey] = useState(false)
  const [confirmTransfer, setConfirmTransfer] = useState(false)
  const [confirmOpenAiTransfer, setConfirmOpenAiTransfer] = useState(false)
  const [consentChecked, setConsentChecked] = useState(false)
  const [openAiConsentChecked, setOpenAiConsentChecked] = useState(false)
  const [budgetEnabled, setBudgetEnabled] = useState<boolean | null>(null)
  const [hardStop, setHardStop] = useState<string | null>(null)
  const [softRemind, setSoftRemind] = useState<string | null>(null)
  const [budgetPeriod, setBudgetPeriod] = useState<'30d' | 'calendar_month' | null>(null)
  const [unknownUsagePolicy, setUnknownUsagePolicy] = useState<'deny' | 'confirm' | null>(null)
  const [historyStart, setHistoryStart] = useState('')
  const [historyEnd, setHistoryEnd] = useState('')
  const [historyRange, setHistoryRange] = useState<{ start: string; end: string } | null>(null)
  const [historyRangeError, setHistoryRangeError] = useState<string | null>(null)
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false)
  const [diagnosticsMessage, setDiagnosticsMessage] = useState<string | null>(null)
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null)
  const [logCleanupMessage, setLogCleanupMessage] = useState<string | null>(null)
  const [logCleanupError, setLogCleanupError] = useState<string | null>(null)

  const query = useQuery({ queryKey: ['ai-provider'], queryFn: ({ signal }) => getAiProviderStatus(signal) })
  const storageQuery = useQuery({ queryKey: ['system-storage'], queryFn: ({ signal }) => getStorageOverview(signal) })
  const modelQuery = useQuery({
    queryKey: ['embedding-model-status'],
    queryFn: ({ signal }) => getEmbeddingModelStatus(signal),
  })
  const usageQuery = useQuery({ queryKey: ['ai-usage'], queryFn: ({ signal }) => getAiUsageSummary(signal) })
  const historyUsageQuery = useQuery({
    queryKey: ['ai-usage-window', historyRange],
    queryFn: ({ signal }) => {
      if (!historyRange) throw new Error('需要选择历史窗口。')
      return getAiUsageSummary(signal, {
        start: `${historyRange.start}T00:00:00Z`,
        end: `${historyRange.end}T00:00:00Z`,
      })
    },
    enabled: historyRange !== null,
    retry: false,
  })
  const budgetQuery = useQuery({
    queryKey: ['ai-budget'],
    queryFn: ({ signal }) => getAiBudgetStatus(signal),
  })
  const privacyQuery = useQuery({ queryKey: ['system-privacy'], queryFn: ({ signal }) => getPrivacyStatus(signal) })
  const diagnosticsPreviewQuery = useQuery({
    queryKey: ['system-diagnostics-preview'],
    queryFn: ({ signal }) => getDiagnosticsPreview(signal),
    enabled: false,
    retry: false,
  })
  const backupsQuery = useQuery({
    queryKey: ['system-backups'],
    queryFn: ({ signal }) => listBackups(signal),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      return items.some((item) => isBackupInProgress(item.status)) ? 1500 : false
    },
  })

  const [backupMessage, setBackupMessage] = useState<string | null>(null)
  const [backupError, setBackupError] = useState<string | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

  const status = query.data
  const budgetEnabledValue = budgetEnabled ?? budgetQuery.data?.budget.enabled ?? false
  const hardStopValue = hardStop ?? budgetQuery.data?.budget.hard_stop_usd ?? ''
  const softRemindValue = softRemind ?? budgetQuery.data?.budget.soft_remind_usd ?? ''
  const budgetPeriodValue = budgetPeriod ?? (budgetQuery.data?.budget.period === 'calendar_month' ? 'calendar_month' : '30d')
  const unknownUsagePolicyValue = unknownUsagePolicy ?? budgetQuery.data?.budget.unknown_usage_policy ?? 'deny'

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['ai-provider'] })
  const saveMutation = useMutation({
    mutationFn: saveAiProviderKey,
    onSettled: () => {
      setApiKey('')
      setShowKey(false)
      void refresh()
    },
  })
  const deleteMutation = useMutation({
    mutationFn: deleteAiProviderKey,
    onSuccess: () => {
      setConfirmTransfer(false)
      void refresh()
    },
  })
  const testMutation = useMutation({
    mutationFn: () => testAiProviderConnection(true),
    onSuccess: () => void refresh(),
    onError: () => void refresh(),
  })
  const consentMutation = useMutation({
    mutationFn: (version: string) => acceptExternalAiConsent(version),
    onSuccess: () => {
      setConsentChecked(false)
      void refresh()
    },
  })
  const modeMutation = useMutation({
    mutationFn: (mode: GenerationMode) => setAiGenerationMode(mode),
    onSuccess: () => void refresh(),
  })
  const saveOpenAiMutation = useMutation({
    mutationFn: saveOpenAiProviderKey,
    onSettled: () => {
      setOpenAiKey('')
      setShowOpenAiKey(false)
      void refresh()
    },
  })
  const deleteOpenAiMutation = useMutation({
    mutationFn: deleteOpenAiProviderKey,
    onSuccess: () => {
      setConfirmOpenAiTransfer(false)
      void refresh()
    },
  })
  const testOpenAiMutation = useMutation({
    mutationFn: () => testOpenAiProviderConnection(true),
    onSuccess: () => void refresh(),
    onError: () => void refresh(),
  })
  const openAiConsentMutation = useMutation({
    mutationFn: (version: string) => acceptOpenAiConsent(version),
    onSuccess: () => {
      setOpenAiConsentChecked(false)
      void refresh()
    },
  })
  const budgetMutation = useMutation({
    mutationFn: () =>
      updateAiBudget({
        enabled: budgetEnabledValue,
        hard_stop_usd: hardStopValue.trim() || null,
        soft_remind_usd: softRemindValue.trim() || null,
        period: budgetPeriodValue,
        unknown_usage_policy: unknownUsagePolicyValue,
      }),
    onSuccess: () => {
      setBudgetEnabled(null)
      setHardStop(null)
      setSoftRemind(null)
      setBudgetPeriod(null)
      setUnknownUsagePolicy(null)
      void queryClient.invalidateQueries({ queryKey: ['ai-budget'] })
      void queryClient.invalidateQueries({ queryKey: ['ai-usage'] })
    },
  })
  const createBackupMutation = useMutation({
    mutationFn: () => createBackup(),
    onMutate: () => {
      setBackupError(null)
      setBackupMessage(null)
    },
    onSuccess: (backup) => {
      setBackupMessage(
        backup.status === 'COMPLETED'
          ? '备份已完成，可下载到本地保存。'
          : '备份任务已持久化。可以离开此页面，稍后回来查看状态。',
      )
      void queryClient.invalidateQueries({ queryKey: ['system-backups'] })
    },
    onError: (error) => {
      setBackupError(errorText(error))
    },
  })
  const retryBackupMutation = useMutation({
    mutationFn: (backupId: string) => retryBackup(backupId),
    onMutate: () => {
      setBackupError(null)
      setBackupMessage(null)
    },
    onSuccess: (backup) => {
      setBackupMessage('备份重试任务已持久化。状态会在任务完成后更新。')
      queryClient.setQueryData(
        ['system-backups'],
        (current: { items: BackupRecord[] } | undefined) =>
          current
            ? {
                ...current,
                items: current.items.map((item) =>
                  item.backup_id === backup.backup_id ? backup : item,
                ),
              }
            : current,
      )
      void queryClient.invalidateQueries({ queryKey: ['system-backups'] })
    },
    onError: (error) => setBackupError(errorText(error)),
  })
  const diagnosticsDownloadMutation = useMutation({
    mutationFn: () => downloadDiagnostics(),
    onMutate: () => {
      setDiagnosticsError(null)
      setDiagnosticsMessage(null)
    },
    onSuccess: () => setDiagnosticsMessage('诊断包已开始下载，请保存在本机。'),
    onError: (error) => setDiagnosticsError(errorText(error)),
  })
  const logCleanupMutation = useMutation({
    mutationFn: clearDiagnosticLogs,
    onMutate: () => {
      setLogCleanupError(null)
      setLogCleanupMessage(null)
    },
    onSuccess: (result) => {
      setLogCleanupMessage(
        result.complete
          ? result.files_removed > 0
            ? `已清理 ${result.files_removed} 个诊断日志文件，释放 ${formatBytes(result.bytes_removed)}。`
            : '没有可清理的诊断日志。'
          : `已清理 ${result.files_removed} 个文件；${result.remaining_files} 个正在使用的文件暂时保留。`,
      )
      void queryClient.invalidateQueries({ queryKey: ['system-privacy'] })
    },
    onError: (error) => setLogCleanupError(errorText(error)),
  })

  async function handleDownloadBackup(backup: BackupRecord) {
    setBackupError(null)
    setDownloadingId(backup.backup_id)
    try {
      await downloadBackup(backup.backup_id)
      setBackupMessage('备份包已开始下载。请保存在受保护磁盘，勿上传云端。')
    } catch (error) {
      setBackupError(errorText(error))
    } finally {
      setDownloadingId(null)
    }
  }

  function backupStatusLabel(statusValue: string) {
    if (statusValue === 'COMPLETED') return '已完成'
    if (statusValue === 'FAILED') return '失败'
    if (statusValue === 'QUEUED') return '排队中'
    if (statusValue === 'RUNNING' || statusValue === 'CREATING') return '正在创建'
    return statusValue
  }

  const busy =
    saveMutation.isPending ||
    deleteMutation.isPending ||
    testMutation.isPending ||
    consentMutation.isPending ||
    modeMutation.isPending ||
    budgetMutation.isPending ||
    saveOpenAiMutation.isPending ||
    deleteOpenAiMutation.isPending ||
    testOpenAiMutation.isPending ||
    openAiConsentMutation.isPending
  const generationMode = status?.generation_mode ?? 'mock'
  const openAi = status?.providers?.find((item) => item.provider_id === 'openai_gpt6_sol')
  const budgetAllowsProbe = Boolean(
    !budgetQuery.isLoading && !budgetQuery.isError && !budgetQuery.data?.hard_stop_would_block,
  )
  const canTest = Boolean(status?.configured && status.credential_store.available && confirmTransfer && !busy && budgetAllowsProbe)
  const canTestOpenAi = Boolean(openAi?.configured && openAi.credential_store.available && confirmOpenAiTransfer && !busy && budgetAllowsProbe)
  const activeBackup = backupsQuery.data?.items.find((item) => isBackupInProgress(item.status))
  const modeLabel = generationMode === 'deepseek'
    ? 'DeepSeek 在线'
    : generationMode === 'openai_gpt6_sol'
      ? 'OpenAI GPT-6 Sol 在线'
      : 'Mock'

  if (query.isLoading) {
    return (
      <section className="settings-page">
        <LoadingBlock label="正在读取 AI 服务状态" />
      </section>
    )
  }

  if (query.isError || !status) {
    return (
      <section className="settings-page">
        <FailBlock error={query.error} onRetry={() => void query.refetch()} />
      </section>
    )
  }

  const modelState = modelQuery.data?.state
  const modelLabel =
    modelState === 'READY'
      ? 'READY'
      : modelState === 'MISSING_OFFLINE' || modelState === 'MISSING'
        ? 'MISSING'
        : modelState ?? (modelQuery.isError ? '暂时无法读取' : '读取中')

  return (
    <section className="settings-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">本机运行配置</span>
          <h1>设置</h1>
          <p>查看本机存储、模型与用量，并管理 AI 服务凭据。Key 只保存在 Windows 凭据管理器中。</p>
        </div>
      </div>

      <div className="settings-grid">
        <section className="settings-section" aria-labelledby="storage-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon">
                <HardDrive size={18} aria-hidden="true" />
              </span>
              <h2 id="storage-heading">数据存储与空间</h2>
              <p>只读展示本机数据目录分类占用，不接受网页传入任意路径。</p>
            </div>
          </div>
          {storageQuery.isLoading ? <LoadingBlock label="正在读取存储信息" /> : null}
          {storageQuery.isError ? (
            <FailBlock error={storageQuery.error} onRetry={() => void storageQuery.refetch()} />
          ) : null}
          {storageQuery.data ? (
            <>
              <div className="settings-provider-meta">
                <span>数据目录：{storageQuery.data.data_dir_display}</span>
                <span>数据库：{storageQuery.data.database}</span>
                <span>可写：{storageQuery.data.writable ? '是' : '否'}</span>
                <span>
                  合计：
                  {storageQuery.data.total_byte_size == null
                    ? '暂时无法读取'
                    : formatBytes(storageQuery.data.total_byte_size)}
                </span>
              </div>
              {storageQuery.data.message ? <p className="settings-hint">{storageQuery.data.message}</p> : null}
              <ul className="settings-stat-list">
                {storageQuery.data.categories.map((item) => (
                  <li key={item.key}>
                    <span>{item.label}</span>
                    <strong>{item.available ? formatBytes(item.byte_size) : item.message ?? '暂时无法读取'}</strong>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>

        <section className="settings-section" aria-labelledby="embedding-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon">
                <Cpu size={18} aria-hidden="true" />
              </span>
              <h2 id="embedding-heading">本地 Embedding 模型</h2>
              <p>展示本机固定 ONNX 模型状态；安装与校验继续使用知识库中的模型管理入口。</p>
            </div>
            <span className={`settings-state ${modelState === 'READY' ? 'settings-state--ready' : ''}`}>
              {modelQuery.isLoading ? '读取中' : modelLabel}
            </span>
          </div>
          {modelQuery.isError ? (
            <FailBlock error={modelQuery.error} onRetry={() => void modelQuery.refetch()} />
          ) : null}
          {modelQuery.data ? (
            <>
              <div className="settings-provider-meta">
                <span>基础模型：{modelQuery.data.base_model_id}</span>
                <span>产物 revision：{modelQuery.data.artifact_revision}</span>
                <span>大小：{formatBytes(modelQuery.data.total_size_bytes)}</span>
              </div>
              <p className="settings-hint">
                当前状态为真实本机检测结果。如需安装或重试，请前往知识库详情中的模型管理，不在此页重新下载。
              </p>
              <Link className="quiet-button" to="/knowledge-bases">
                打开知识库模型入口
              </Link>
            </>
          ) : null}
        </section>

        <section className="settings-section" aria-labelledby="ai-provider-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon">
                <KeyRound size={18} aria-hidden="true" />
              </span>
              <h2 id="ai-provider-heading">AI 服务配置</h2>
              <p>
                手动选择 Mock、DeepSeek <code>{status.requested_model}</code> 或 OpenAI <code>gpt-6-sol</code>。
                切换按钮本身不联网。
              </p>
            </div>
            <span className={`settings-state ${status.configured ? 'settings-state--ready' : ''}`}>
              {status.configured ? <Check size={14} aria-hidden="true" /> : <CircleAlert size={14} aria-hidden="true" />}
              {status.configured ? '已配置' : '未配置 / 需要重新配置'}
            </span>
          </div>

          <div className="settings-provider-meta">
            <span>Provider：{status.display_name}</span>
            <span>存储：{status.credential_store.available ? 'Windows Credential Manager' : '不可用'}</span>
            <span>生成模式：{modeLabel}</span>
          </div>
          <div className="settings-mode-actions">
            <button
              className="quiet-button"
              type="button"
              disabled={busy || generationMode === 'mock'}
              onClick={() => modeMutation.mutate('mock')}
            >
              使用 Mock（无费用）
            </button>
            <button
              className="quiet-button"
              type="button"
              disabled={busy || generationMode === 'deepseek'}
              onClick={() => modeMutation.mutate('deepseek')}
            >
              使用 DeepSeek 在线生成
            </button>
            <button
              className="quiet-button"
              type="button"
              disabled={busy || generationMode === 'openai_gpt6_sol'}
              onClick={() => modeMutation.mutate('openai_gpt6_sol')}
            >
              使用 OpenAI GPT-6 Sol
            </button>
          </div>
          <p className="settings-hint">
            {status.account_notice ?? 'OpenAI 和 DeepSeek 是两套不同账户、API Key 和账单。'}
            {' '}
            {status.learning_notice ?? '新建学习会话使用当前选择。Mock 仍按本地规则出题和评分，不会外发。在线模式会在创建题目和提交答案前分别确认本次费用。已经创建的会话保持创建时的服务。这仍不是完整学习计划或复习。'}
          </p>
          {generationMode === 'deepseek' ? (
            <div className="settings-privacy-copy">
              <p>DeepSeek 在线生成、会外发当前问题与必要的少量证据。</p>
              {status.cost_estimate ? (
                <p>
                  {status.cost_estimate.disclaimer} 知识库问题按本地上限粗估不超过{' '}
                  {status.cost_estimate.knowledge_question_estimated_usd_ceiling} 美元；连接探测粗估不超过{' '}
                  {status.cost_estimate.probe_estimated_usd_ceiling} 美元。假设：{status.cost_estimate.rate_assumption}。
                </p>
              ) : null}
            </div>
          ) : generationMode === 'openai_gpt6_sol' ? (
            <div className="settings-privacy-copy">
              <p>OpenAI GPT-6 Sol 在线生成、会外发当前问题与必要的少量证据。API 费用由 OpenAI Platform 单独结算。</p>
              <p>{openAi?.cost_estimate?.disclaimer ?? '价格是带日期的估算，不是 OpenAI 账单。'}</p>
              {openAi?.configured ? null : <p>OpenAI 未配置 / 不可用。需要官方 Platform Key，不能借用其他产品额度。</p>}
            </div>
          ) : (
            <p className="settings-hint">当前是 Mock。启动、刷新和发送都不会调用 DeepSeek 或 OpenAI，也不会产生费用。</p>
          )}
          {modeMutation.isError && (
            <p className="settings-error-text" role="alert">
              {errorText(modeMutation.error)}
            </p>
          )}

          <form
            className="settings-key-form"
            onSubmit={(event) => {
              event.preventDefault()
              if (apiKey.trim()) saveMutation.mutate(apiKey.trim())
            }}
          >
            <label htmlFor="deepseek-api-key">DeepSeek API Key</label>
            <div className="settings-key-input">
              <input
                id="deepseek-api-key"
                type={showKey ? 'text' : 'password'}
                autoComplete="off"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={status.configured ? '已配置；输入新 Key 可覆盖' : '粘贴 API Key'}
                spellCheck={false}
              />
              <button
                className="icon-button icon-button--small"
                type="button"
                onClick={() => setShowKey((value) => !value)}
                aria-label={showKey ? '隐藏 API Key' : '显示 API Key'}
                title={showKey ? '隐藏 API Key' : '显示 API Key'}
              >
                {showKey ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
              </button>
            </div>
            <p className="settings-hint">保存后输入框会清空，页面不会读取或回显已保存的完整 Key。</p>
            {saveMutation.isError && (
              <p className="settings-error-text" role="alert">
                {errorText(saveMutation.error)}
              </p>
            )}
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={!apiKey.trim() || busy}>
                <KeyRound size={15} aria-hidden="true" />
                {saveMutation.isPending ? '正在保存' : '保存 Key'}
              </button>
              <button
                className="danger-button"
                type="button"
                disabled={!status.configured || busy}
                onClick={() => deleteMutation.mutate()}
              >
                <Trash2 size={15} aria-hidden="true" />
                {deleteMutation.isPending ? '正在删除' : '删除本地 Key'}
              </button>
            </div>
          </form>

          <div className="settings-links">
            <a href={status.source_url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} aria-hidden="true" />
              获取 API Key
            </a>
            <a href={status.pricing_url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} aria-hidden="true" />
              查看官方价格
            </a>
          </div>

          <form
            className="settings-key-form"
            onSubmit={(event) => {
              event.preventDefault()
              if (openAiKey.trim()) saveOpenAiMutation.mutate(openAiKey.trim())
            }}
          >
            <label htmlFor="openai-api-key">OpenAI API Key</label>
            <p className="settings-hint">
              {openAi?.configured ? 'OpenAI Key 已配置' : 'OpenAI 未配置 / 不可用'}。删除或覆盖这一家不会影响 DeepSeek。
              {openAi?.billing_note ? ` ${openAi.billing_note}` : ' API 费用由 OpenAI Platform 单独结算。'}
            </p>
            <div className="settings-key-input">
              <input
                id="openai-api-key"
                type={showOpenAiKey ? 'text' : 'password'}
                autoComplete="off"
                value={openAiKey}
                onChange={(event) => setOpenAiKey(event.target.value)}
                placeholder={openAi?.configured ? '已配置；输入新 Key 可覆盖' : '粘贴 OpenAI Platform API Key'}
                spellCheck={false}
              />
              <button
                className="icon-button icon-button--small"
                type="button"
                onClick={() => setShowOpenAiKey((value) => !value)}
                aria-label={showOpenAiKey ? '隐藏 OpenAI API Key' : '显示 OpenAI API Key'}
              >
                {showOpenAiKey ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
              </button>
            </div>
            {saveOpenAiMutation.isError ? (
              <p className="settings-error-text" role="alert">{errorText(saveOpenAiMutation.error)}</p>
            ) : null}
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={!openAiKey.trim() || busy}>
                {saveOpenAiMutation.isPending ? '正在保存 OpenAI Key' : '保存 OpenAI Key'}
              </button>
              <button
                className="danger-button"
                type="button"
                disabled={!openAi?.configured || busy}
                onClick={() => deleteOpenAiMutation.mutate()}
              >
                {deleteOpenAiMutation.isPending ? '正在删除 OpenAI Key' : '删除 OpenAI Key'}
              </button>
            </div>
          </form>
          <div className="settings-links">
            <a href={openAi?.source_url ?? 'https://platform.openai.com/api-keys'} target="_blank" rel="noreferrer">
              <ExternalLink size={14} aria-hidden="true" />
              获取 OpenAI API Key
            </a>
            <a href={openAi?.pricing_url ?? 'https://developers.openai.com/api/docs/models/gpt-6-sol'} target="_blank" rel="noreferrer">
              <ExternalLink size={14} aria-hidden="true" />
              查看 OpenAI 价格（{openAi?.cost_estimate.checked_on ?? '2026-09-27'}）
            </a>
          </div>
        </section>

        <section className="settings-section" aria-labelledby="usage-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon">
                <Wallet size={18} aria-hidden="true" />
              </span>
              <h2 id="usage-heading">本地用量与预算</h2>
              <p>按 UTC 预算周期统计 Chat、RAG 与学习操作；费用由所选 Provider 账户结算。</p>
            </div>
          </div>
          {usageQuery.isLoading || budgetQuery.isLoading ? <LoadingBlock label="正在读取用量与预算" /> : null}
          {usageQuery.isError ? (
            <FailBlock error={usageQuery.error} onRetry={() => void usageQuery.refetch()} />
          ) : null}
          {budgetQuery.isError ? (
            <FailBlock error={budgetQuery.error} onRetry={() => void budgetQuery.refetch()} />
          ) : null}
          {usageQuery.data ? (
            <>
              <div className="settings-provider-meta">
                <span>Mock 操作：{usageQuery.data.totals.mock.operations}</span>
                <span>
                  Mock Token：输入 {usageQuery.data.totals.mock.input_tokens} / 输出{' '}
                  {usageQuery.data.totals.mock.output_tokens}
                </span>
                <span>在线操作：{usageQuery.data.totals.online.operations}</span>
                {(usageQuery.data.by_provider ?? [])
                  .filter((item) => item.provider === 'DEEPSEEK' || item.provider === 'OPENAI')
                  .map((item) => (
                    <span key={item.provider}>
                      {item.provider === 'OPENAI' ? 'OpenAI' : 'DeepSeek'}：{item.operations} 次；本地估算{' '}
                      {item.estimated_usd ?? '未知'}；未知用量 {item.unknown_usage_operations} 次
                    </span>
                  ))}
                <span>
                  已知 usage 本地估算：
                  {usageQuery.data.estimated_online_usd == null
                    ? '尚无统计'
                    : `${usageQuery.data.estimated_online_usd} ${usageQuery.data.currency}`}
                </span>
                <span>未发送预留：{usageQuery.data.reserved_online_usd} {usageQuery.data.currency}</span>
                <span>已外发未知预估：{usageQuery.data.unknown_exposure_estimated_usd} {usageQuery.data.currency}</span>
                <span>
                  窗口（UTC）：{usageQuery.data.window_start} 至 {usageQuery.data.window_end}
                </span>
                <span>最近核对：{usageQuery.data.checked_at}</span>
              </div>
              {usageQuery.data.online_actual_usage_message ? (
                <p className="settings-hint">{usageQuery.data.online_actual_usage_message}</p>
              ) : null}
              {usageQuery.data.totals.online.unknown_usage_operations > 0 ? (
                <p className="settings-hint">
                  在线有 {usageQuery.data.totals.online.unknown_usage_operations} 次操作的 usage 或价格快照未知；未按零成本放行。
                </p>
              ) : null}
              <p className="settings-hint">
                {usageQuery.data.estimate_disclaimer} {usageQuery.data.billing_reconciliation_status}
              </p>
              <div className="settings-links">
                <a href={usageQuery.data.provider_billing_urls?.deepseek ?? 'https://platform.deepseek.com/usage'} target="_blank" rel="noreferrer">
                  <ExternalLink size={14} aria-hidden="true" />
                  DeepSeek 官方用量与账单
                </a>
                <a href={usageQuery.data.provider_billing_urls?.openai ?? 'https://platform.openai.com/usage'} target="_blank" rel="noreferrer">
                  <ExternalLink size={14} aria-hidden="true" />
                  OpenAI 官方用量与账单
                </a>
                <a href={usageQuery.data.cost_estimates?.deepseek?.pricing_url ?? usageQuery.data.cost_estimate.pricing_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={14} aria-hidden="true" />
                  DeepSeek 当前公开价格（核于 {usageQuery.data.cost_estimates?.deepseek?.checked_on ?? usageQuery.data.cost_estimate.checked_on}）
                </a>
                <a href={usageQuery.data.cost_estimates?.openai?.pricing_url ?? 'https://developers.openai.com/api/docs/models/gpt-6-sol'} target="_blank" rel="noreferrer">
                  <ExternalLink size={14} aria-hidden="true" />
                  OpenAI 当前公开价格（核于 {usageQuery.data.cost_estimates?.openai?.checked_on ?? '未核对'}）
                </a>
                {(usageQuery.data.used_price_sources ?? []).map((source) => (
                  <a key={`${source.provider}-${source.checked_on}-${source.pricing_url}`} href={source.pricing_url} target="_blank" rel="noreferrer">
                    <ExternalLink size={14} aria-hidden="true" />
                    {source.provider} 价格来源（核对于 {source.checked_on}）
                  </a>
                ))}
              </div>
              <p className="settings-hint">
                操作类型：{(usageQuery.data.by_operation_type ?? []).map((item) => `${item.operation_type} ${item.operations} 次`).join('；') || '暂无记录'}
              </p>
              <details>
                <summary>历史窗口</summary>
                <form
                  className="settings-key-form"
                  onSubmit={(event) => {
                    event.preventDefault()
                    setHistoryRangeError(null)
                    if (!historyStart || !historyEnd || historyStart >= historyEnd) {
                      setHistoryRangeError('结束日期必须晚于开始日期。')
                      return
                    }
                    setHistoryRange({ start: historyStart, end: historyEnd })
                  }}
                >
                  <label htmlFor="usage-history-start">开始日期（UTC）</label>
                  <input
                    id="usage-history-start"
                    type="date"
                    value={historyStart}
                    onChange={(event) => setHistoryStart(event.target.value)}
                    required
                  />
                  <label htmlFor="usage-history-end">结束日期（UTC，不包含）</label>
                  <input
                    id="usage-history-end"
                    type="date"
                    value={historyEnd}
                    min={historyStart || undefined}
                    onChange={(event) => setHistoryEnd(event.target.value)}
                    required
                  />
                  {historyRangeError ? <p className="settings-error-text" role="alert">{historyRangeError}</p> : null}
                  <button className="quiet-button" type="submit">查询历史窗口</button>
                </form>
                {historyUsageQuery.isError ? (
                  <FailBlock error={historyUsageQuery.error} onRetry={() => void historyUsageQuery.refetch()} />
                ) : null}
                {historyUsageQuery.data ? (
                  <div className="settings-provider-meta">
                    <span>
                      UTC 窗口：{historyUsageQuery.data.window_start} 至 {historyUsageQuery.data.window_end}
                    </span>
                    <span>已知费用本地估算：{historyUsageQuery.data.estimated_online_usd} {historyUsageQuery.data.currency}</span>
                    <span>预留：{historyUsageQuery.data.reserved_online_usd} {historyUsageQuery.data.currency}</span>
                    <span>未知操作：{historyUsageQuery.data.totals.online.unknown_usage_operations}</span>
                    <span>{historyUsageQuery.data.billing_reconciliation_status}</span>
                  </div>
                ) : null}
              </details>
            </>
          ) : null}
          {budgetQuery.data ? (
            <form
              className="settings-key-form"
              onSubmit={(event) => {
                event.preventDefault()
                budgetMutation.mutate()
              }}
            >
              <label className="settings-checkline">
                <input
                  type="checkbox"
                  checked={budgetEnabledValue}
                  onChange={(event) => setBudgetEnabled(event.target.checked)}
                />
                <span>启用本地硬停止阈值（默认关闭；请求前原子预留）</span>
              </label>
              <label htmlFor="budget-period">预算周期</label>
              <select
                id="budget-period"
                value={budgetPeriodValue}
                onChange={(event) => setBudgetPeriod(event.target.value as '30d' | 'calendar_month')}
              >
                <option value="30d">滚动 30 天（UTC）</option>
                <option value="calendar_month">UTC 自然月</option>
              </select>
              <label htmlFor="budget-hard-stop">硬停止阈值（USD）</label>
              <input
                id="budget-hard-stop"
                value={hardStopValue}
                onChange={(event) => setHardStop(event.target.value)}
                placeholder="例如 1.00"
                disabled={!budgetEnabledValue}
              />
              <label htmlFor="budget-soft-remind">软提醒阈值（USD，可选）</label>
              <input
                id="budget-soft-remind"
                value={softRemindValue}
                onChange={(event) => setSoftRemind(event.target.value)}
                placeholder="例如 0.50"
                disabled={!budgetEnabledValue}
              />
              <label htmlFor="budget-unknown-policy">未知用量或费率策略</label>
              <select
                id="budget-unknown-policy"
                value={unknownUsagePolicyValue}
                onChange={(event) => setUnknownUsagePolicy(event.target.value as 'deny' | 'confirm')}
                disabled={!budgetEnabledValue}
              >
                <option value="deny">拒绝后续外发</option>
                <option value="confirm">每次显示风险并明确确认</option>
              </select>
              <div className="settings-provider-meta">
                <span>币种：{budgetQuery.data.currency}</span>
                <span>已知费用本地估算：{budgetQuery.data.spent_estimated_usd}</span>
                <span>预算暴露估算（含预留）：{budgetQuery.data.budget_exposure_estimated_usd}</span>
                <span>
                  余量：
                  {budgetQuery.data.remaining_estimated_usd == null
                    ? '未启用或尚无阈值'
                    : budgetQuery.data.remaining_estimated_usd}
                </span>
                <span>
                  未知用量策略：{unknownUsagePolicyValue === 'deny' ? '拒绝外发' : '每次确认'}
                </span>
                <span>预算窗口（UTC）：{budgetQuery.data.window_start} 至 {budgetQuery.data.window_end}</span>
                <span>最近核对：{budgetQuery.data.checked_at}</span>
              </div>
              {budgetQuery.data.soft_remind_triggered ? (
                <p className="settings-hint">已触及软提醒阈值。</p>
              ) : null}
              {budgetQuery.data.hard_stop_would_block ? (
                <p className="settings-error-text" role="status">
                  {budgetQuery.data.hard_stop_block_reason ?? '当前硬停止将阻止新的外部 Provider 调用。'}
                </p>
              ) : null}
              {budgetMutation.isError ? (
                <p className="settings-error-text" role="alert">
                  {errorText(budgetMutation.error)}
                </p>
              ) : null}
              <button className="quiet-button" type="submit" disabled={busy}>
                {budgetMutation.isPending ? '正在保存预算' : '保存预算设置'}
              </button>
            </form>
          ) : null}
        </section>

        <section className="settings-section" aria-labelledby="external-ai-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon settings-icon--safe">
                <ShieldCheck size={18} aria-hidden="true" />
              </span>
              <h2 id="external-ai-heading">数据外发说明</h2>
              <p>连接测试和未来 AI 生成都需要明确确认外部 Provider 边界。</p>
            </div>
            <span className={`settings-state ${status.consent.accepted ? 'settings-state--ready' : ''}`}>
              {status.consent.accepted ? '已记录' : '待确认'}
            </span>
          </div>
          <div className="settings-privacy-copy">
            <p>未来启用 AI 生成时，只会发送当前问题、必要上下文和选中的少量证据。</p>
            <p>不会发送整库、原文件、Embedding、向量、数据库、日志或本地绝对路径。API Key 保存在本机系统凭据中。</p>
            <p>DeepSeek 按实际输入和输出 Token 计费；连接测试只发送固定短文本，也会产生极小 API 用量。</p>
          </div>
          {!status.consent.accepted && (
            <label className="settings-checkline">
              <input
                type="checkbox"
                checked={consentChecked}
                onChange={(event) => setConsentChecked(event.target.checked)}
              />
              <span>我已阅读本版本外发说明，并同意未来 AI 功能按上述范围发送必要文本。</span>
            </label>
          )}
          {!status.consent.accepted && (
            <button
              className="quiet-button"
              type="button"
              disabled={!consentChecked || busy}
              onClick={() => consentMutation.mutate(status.consent.current_version)}
            >
              {consentMutation.isPending ? '正在记录' : '确认并记录说明版本'}
            </button>
          )}
          {consentMutation.isError && (
            <p className="settings-error-text" role="alert">
              {errorText(consentMutation.error)}
            </p>
          )}
          {status.consent.accepted && (
            <p className="settings-success-text">
              <Check size={14} aria-hidden="true" />
              已记录版本 {status.consent.version}，时间 {formatTime(status.consent.accepted_at)}
            </p>
          )}
          <div className="settings-privacy-copy">
            <p>OpenAI 需要单独同意。DeepSeek 的同意不能代替向 OpenAI 发送资料。</p>
            <p>
              第一次向 OpenAI 外发前：当前问题、必要上下文，以及知识库模式下至多两段受限证据，可能发送到 OpenAI。
              新建学习会话也会使用这里的选择；Mock 仍是本地规则，在线出题和点评需要分别确认费用。
            </p>
          </div>
          {openAi?.consent.accepted ? (
            <p className="settings-success-text">
              <Check size={14} aria-hidden="true" />
              OpenAI 已记录版本 {openAi.consent.version}
            </p>
          ) : (
            <>
              <p>OpenAI 同意未记录</p>
              <label className="settings-checkline">
                <input
                  type="checkbox"
                  checked={openAiConsentChecked}
                  onChange={(event) => setOpenAiConsentChecked(event.target.checked)}
                />
                <span>我已阅读 OpenAI 外发说明，并同意只向 OpenAI 发送上述必要文本。</span>
              </label>
              <button
                className="quiet-button"
                type="button"
                disabled={!openAiConsentChecked || busy || !openAi}
                onClick={() => openAi && openAiConsentMutation.mutate(openAi.consent.current_version)}
              >
                {openAiConsentMutation.isPending ? '正在记录 OpenAI 同意' : '确认 OpenAI 外发说明'}
              </button>
            </>
          )}
          {openAiConsentMutation.isError ? (
            <p className="settings-error-text" role="alert">{errorText(openAiConsentMutation.error)}</p>
          ) : null}
        </section>

        <section className="settings-section" aria-labelledby="privacy-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon">
                <Database size={18} aria-hidden="true" />
              </span>
              <h2 id="privacy-heading">日志与隐私</h2>
              <p>只展示已实现且可核对的隐私边界；未验收能力不会提供假按钮。</p>
            </div>
          </div>
          {privacyQuery.isLoading ? <LoadingBlock label="正在读取隐私说明" /> : null}
          {privacyQuery.isError ? (
            <FailBlock error={privacyQuery.error} onRetry={() => void privacyQuery.refetch()} />
          ) : null}
          {privacyQuery.data ? (
            <ul className="settings-stat-list">
              <li>
                <span>日志清理</span>
                <strong>{privacyQuery.data.log_retention.message}</strong>
              </li>
              <li>
                <span>诊断导出</span>
                <strong>{privacyQuery.data.diagnostics_export.message}</strong>
              </li>
              <li>
                <span>存储迁移</span>
                <strong>{privacyQuery.data.storage_migration.message}</strong>
              </li>
              <li>
                <span>密钥策略</span>
                <strong>{privacyQuery.data.secrets_policy.message}</strong>
              </li>
            </ul>
          ) : null}
          {privacyQuery.data?.log_retention.available ? (
            <div className="settings-diagnostics" aria-live="polite">
              <div className="settings-actions">
                <button
                  className="quiet-button"
                  type="button"
                  disabled={logCleanupMutation.isPending}
                  onClick={() => {
                    const confirmed = window.confirm(
                      '清理会永久删除应用自己的本地结构化诊断日志。会话、任务、业务数据、备份、模型和索引不会受影响。继续吗？',
                    )
                    if (confirmed) logCleanupMutation.mutate()
                  }}
                >
                  <Trash2 size={15} aria-hidden="true" />
                  {logCleanupMutation.isPending ? '正在清理诊断日志' : '清理可清理的诊断日志'}
                </button>
                <span className="settings-hint">
                  当前 {privacyQuery.data.log_retention.file_count} 个文件 /{' '}
                  {formatBytes(privacyQuery.data.log_retention.bytes_used)}；上限{' '}
                  {privacyQuery.data.log_retention.retention_days} 天或{' '}
                  {formatBytes(privacyQuery.data.log_retention.max_bytes)}
                </span>
              </div>
              {logCleanupMessage ? (
                <p className="settings-success-text" role="status">
                  <Check size={14} aria-hidden="true" />{logCleanupMessage}
                </p>
              ) : null}
              {logCleanupError ? (
                <p className="settings-error-text" role="alert">
                  <CircleAlert size={14} aria-hidden="true" />{logCleanupError}
                </p>
              ) : null}
            </div>
          ) : null}
          {privacyQuery.data?.diagnostics_export.available ? (
            <div className="settings-diagnostics" aria-live="polite">
              <p className="settings-hint">
                诊断包只包含安全状态投影；预览与下载内容一致，保存在本机，不会自动上传。
              </p>
              <div className="settings-actions">
                <button
                  className="quiet-button"
                  type="button"
                  onClick={() => {
                    if (diagnosticsOpen) {
                      setDiagnosticsOpen(false)
                      void queryClient.cancelQueries({ queryKey: ['system-diagnostics-preview'] })
                      return
                    }
                    setDiagnosticsError(null)
                    setDiagnosticsOpen(true)
                    void diagnosticsPreviewQuery.refetch()
                  }}
                >
                  <Eye size={15} aria-hidden="true" />
                  {diagnosticsOpen ? '关闭诊断预览' : '预览诊断内容'}
                </button>
                <button
                  className="primary-button"
                  type="button"
                  disabled={diagnosticsDownloadMutation.isPending}
                  onClick={() => diagnosticsDownloadMutation.mutate()}
                >
                  <Download size={15} aria-hidden="true" />
                  {diagnosticsDownloadMutation.isPending ? '正在准备诊断包' : '导出诊断包'}
                </button>
              </div>
              {diagnosticsOpen && diagnosticsPreviewQuery.isFetching ? (
                <LoadingBlock label="正在生成安全诊断预览" />
              ) : null}
              {diagnosticsOpen && diagnosticsPreviewQuery.isError ? (
                <p className="settings-error-text" role="alert">
                  {errorText(diagnosticsPreviewQuery.error)}
                </p>
              ) : null}
              {diagnosticsOpen && diagnosticsPreviewQuery.data ? (
                <div className="settings-diagnostics__preview">
                  <div className="settings-stat-list">
                    <div>
                      <span>预计体积</span>
                      <strong>{formatBytes(diagnosticsPreviewQuery.data.estimated_size_bytes)}</strong>
                    </div>
                    <div>
                      <span>任务记录</span>
                      <strong>
                        {diagnosticsPreviewQuery.data.task_summary.recent_count} /{' '}
                        {diagnosticsPreviewQuery.data.task_summary.total_count}
                        {diagnosticsPreviewQuery.data.task_summary.truncated ? '（仅最近 50 条）' : ''}
                      </strong>
                    </div>
                    <div>
                      <span>生成时间</span>
                      <strong>{formatTime(diagnosticsPreviewQuery.data.generated_at)}</strong>
                    </div>
                  </div>
                  <p className="settings-hint">包含：{diagnosticsPreviewQuery.data.included_categories.join('；')}</p>
                  <p className="settings-hint">明确排除：{diagnosticsPreviewQuery.data.excluded_categories.join('；')}</p>
                  <details>
                    <summary>查看脱敏任务状态</summary>
                    {diagnosticsPreviewQuery.data.projection.tasks.items.length > 0 ? (
                      <ul className="settings-diagnostics__tasks">
                        {diagnosticsPreviewQuery.data.projection.tasks.items.map((task) => (
                          <li key={task.diagnostic_id}>
                            <span>{task.task_type}</span>
                            <strong>{task.status}{task.phase ? ` · ${task.phase}` : ''}</strong>
                            {task.error_code ? <small>原因码：{task.error_code}</small> : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="settings-hint">暂无任务记录。</p>
                    )}
                  </details>
                  <button className="quiet-button" type="button" onClick={() => setDiagnosticsOpen(false)}>
                    取消预览
                  </button>
                </div>
              ) : null}
              {diagnosticsMessage ? <p className="settings-success-text"><Check size={14} aria-hidden="true" />{diagnosticsMessage}</p> : null}
              {diagnosticsError ? <p className="settings-error-text" role="alert"><CircleAlert size={14} aria-hidden="true" />{diagnosticsError}</p> : null}
            </div>
          ) : null}
        </section>

        <section className="settings-section settings-section--probe" aria-labelledby="probe-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon">
                <Wifi size={18} aria-hidden="true" />
              </span>
              <h2 id="probe-heading">连接探测</h2>
              <p>只在你主动点击并确认外发后发送固定短文本，不会带入文件或会话内容。</p>
            </div>
            {status.probe && (
              <span
                className={`settings-state ${status.probe.status === 'success' ? 'settings-state--ready' : 'settings-state--error'}`}
              >
                {status.probe.status === 'success' ? '成功' : '失败'}
              </span>
            )}
          </div>
          <label className="settings-checkline settings-checkline--probe">
            <input
              type="checkbox"
              checked={confirmTransfer}
              onChange={(event) => setConfirmTransfer(event.target.checked)}
            />
            <span>
              {budgetQuery.data?.budget.enabled
                && budgetQuery.data.budget?.unknown_usage_policy === 'confirm'
                && (budgetQuery.data.usage_summary?.unknown_usage_operations ?? 0) > 0
                ? '我确认向 DeepSeek 发送固定测试文本、接受极小用量，并接受历史未知用量带来的估算风险。'
                : '我确认本次会向 DeepSeek 发送固定测试文本，并接受极小 API 用量。'}
            </span>
          </label>
          {budgetQuery.data?.hard_stop_block_reason ? (
            <p className="settings-error-text" role="status">{budgetQuery.data.hard_stop_block_reason}</p>
          ) : null}
          {budgetQuery.isError ? <p className="settings-error-text" role="status">本地预算状态读取失败，暂不能确认是否允许连接探测。</p> : null}
          <button className="primary-button" type="button" disabled={!canTest} onClick={() => testMutation.mutate()}>
            <Wifi size={15} aria-hidden="true" />
            {testMutation.isPending ? '正在测试连接' : '测试连接'}
          </button>
          {testMutation.isError && (
            <p className="settings-error-text" role="alert">
              {errorText(testMutation.error)}
            </p>
          )}
          {status.probe && (
            <div
              className={`settings-probe-result ${status.probe.status === 'success' ? 'settings-probe-result--success' : 'settings-probe-result--failure'}`}
            >
              <div>
                <span>最近检查</span>
                <strong>{formatTime(status.probe.checked_at)}</strong>
              </div>
              <div>
                <span>请求别名</span>
                <strong>{status.probe.requested_model}</strong>
              </div>
              <div>
                <span>实际模型</span>
                <strong>{status.probe.resolved_model ?? '未返回'}</strong>
              </div>
              <div>
                <span>流式能力</span>
                <Capability value={status.probe.stream_supported} />
              </div>
              <div>
                <span>Usage 字段</span>
                <Capability value={status.probe.usage_supported} />
              </div>
              <div>
                <span>本次 Token</span>
                <strong>
                  {status.probe.usage
                    ? `输入 ${status.probe.usage.prompt_tokens ?? 0} · 输出 ${status.probe.usage.completion_tokens ?? 0}`
                    : '未返回'}
                </strong>
              </div>
              {status.probe.error_detail && <p>{status.probe.error_detail}</p>}
            </div>
          )}
          {status.probe?.status === 'success' && (
            <p className="settings-hint">
              探测成功只说明这次请求可用，不代表账户余额充足，也不代表正式聊天已经开启。
            </p>
          )}
          <h3>OpenAI 连接探测</h3>
          <p className="settings-hint">只在你主动点击并确认费用后发送一条测试请求。不会自动探测，也不会改用 DeepSeek。</p>
          <label className="settings-checkline settings-checkline--probe">
            <input
              type="checkbox"
              checked={confirmOpenAiTransfer}
              onChange={(event) => setConfirmOpenAiTransfer(event.target.checked)}
            />
            <span>
              {budgetQuery.data?.budget.enabled
                && budgetQuery.data.budget?.unknown_usage_policy === 'confirm'
                && (budgetQuery.data.usage_summary?.unknown_usage_operations ?? 0) > 0
                ? '我确认向 OpenAI 发送测试请求、接受可能费用，并接受历史未知用量带来的估算风险。'
                : '我确认本次会向 OpenAI 发送一条测试请求，并接受可能产生的 API 费用。'}
            </span>
          </label>
          <button className="primary-button" type="button" disabled={!canTestOpenAi} onClick={() => testOpenAiMutation.mutate()}>
            {testOpenAiMutation.isPending ? '正在测试 OpenAI' : '测试 OpenAI 连接'}
          </button>
          {testOpenAiMutation.isError ? (
            <p className="settings-error-text" role="alert">{errorText(testOpenAiMutation.error)}</p>
          ) : null}
          {openAi?.probe ? (
            <div className={`settings-probe-result ${openAi.probe.status === 'success' ? 'settings-probe-result--success' : 'settings-probe-result--failure'}`}>
              <div>
                <span>OpenAI 最近检查</span>
                <strong>{formatTime(openAi.probe.checked_at)}</strong>
              </div>
              <div>
                <span>请求别名</span>
                <strong>{openAi.probe.requested_model}</strong>
              </div>
              <div>
                <span>实际模型</span>
                <strong>{openAi.probe.resolved_model ?? '未返回'}</strong>
              </div>
              {openAi.probe.error_detail ? <p>{openAi.probe.error_detail}</p> : null}
            </div>
          ) : (
            <p className="settings-hint">OpenAI 最近探测：尚未测试。未配置时显示不可用。</p>
          )}
        </section>

        <section className="settings-section settings-section--probe" aria-labelledby="backup-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon">
                <HardDrive size={18} aria-hidden="true" />
              </span>
              <h2 id="backup-heading">备份</h2>
              <p>一致性本地备份：数据库快照、托管文件与必要解析产物；不含密钥、模型缓存与日志。</p>
            </div>
            <span
              className={`settings-state${
                backupsQuery.data?.items.some((item) => item.status === 'COMPLETED')
                  ? ' settings-state--ready'
                  : backupsQuery.data?.items.some((item) => item.status === 'FAILED')
                    ? ' settings-state--error'
                    : ''
              }`}
            >
              {backupsQuery.isLoading
                ? '读取中'
                : activeBackup
                  ? backupStatusLabel(activeBackup.status)
                  : backupsQuery.data?.items[0]
                    ? backupStatusLabel(backupsQuery.data.items[0].status)
                    : '尚未备份'}
            </span>
          </div>

          <div className="settings-privacy-copy settings-backup-warning" role="note">
            <p>
              <strong>未加密警告：</strong>
              {backupsQuery.data?.warning_message ||
                '此备份包未加密，并包含用户文件与学习历史。请保存在受保护磁盘上，不要上传到云端或共享给他人。'}
            </p>
            <p>范围：SQLite 一致性快照、数据库引用的托管文件、必要解析产物、非秘密配置。向量/FTS/模型/日志/密钥默认排除，恢复后需重建索引。</p>
          </div>

          {backupsQuery.isLoading && <LoadingBlock label="正在读取备份记录…" />}
          {backupsQuery.isError && <FailBlock error={backupsQuery.error} onRetry={() => void backupsQuery.refetch()} />}

          {backupsQuery.data && backupsQuery.data.items.length > 0 && (
            <ul className="settings-backup-list">
              {backupsQuery.data.items.map((backup) => (
                <li key={backup.backup_id} className="settings-backup-item">
                  <div className="settings-backup-item__meta">
                    <strong>{backupStatusLabel(backup.status)}</strong>
                    <span>{formatTime(backup.created_at)}</span>
                    <span>
                      {backup.file_count} 个文件 · {formatBackupSize(backup.total_size)}
                    </span>
                    {backup.unencrypted_warning && <span className="settings-backup-flag">未加密 · 含用户资料</span>}
                    {backup.error_summary && <span className="settings-error-text">{backup.error_summary}</span>}
                  </div>
                  <div className="settings-actions">
                    {backup.status === 'FAILED' && (
                      <button
                        className="quiet-button"
                        type="button"
                        disabled={retryBackupMutation.isPending || Boolean(activeBackup)}
                        onClick={() => retryBackupMutation.mutate(backup.backup_id)}
                      >
                        {retryBackupMutation.isPending ? '正在重试…' : '重试备份'}
                      </button>
                    )}
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={!backup.download_available || downloadingId === backup.backup_id}
                      onClick={() => void handleDownloadBackup(backup)}
                    >
                      {downloadingId === backup.backup_id ? '下载中…' : '下载备份包'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {backupMessage && (
            <p className="settings-success-text">
              <Check size={14} aria-hidden="true" />
              {backupMessage}
            </p>
          )}
          {backupError && (
            <p className="settings-error-text" role="alert">
              <CircleAlert size={14} aria-hidden="true" />
              {backupError}
            </p>
          )}

          <div className="settings-actions">
            <button
              className="primary-button"
              type="button"
              disabled={createBackupMutation.isPending || backupsQuery.data?.items.some((item) => isBackupInProgress(item.status))}
              onClick={() => createBackupMutation.mutate()}
            >
              {createBackupMutation.isPending ? '正在创建备份…' : '创建备份'}
            </button>
          </div>
          <BackupRestorePanel enabled={Boolean(backupsQuery.data?.restore_available)} />
          <p className="settings-hint">
            创建过程使用 SQLite 在线备份 API 与显式清单。恢复在重启后切换数据目录，失败会回到旧数据。
          </p>
        </section>
      </div>
    </section>
  )
}
