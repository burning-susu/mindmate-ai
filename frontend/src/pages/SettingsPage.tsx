import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CircleAlert, ExternalLink, Eye, EyeOff, KeyRound, LoaderCircle, ShieldCheck, Trash2, Wifi } from 'lucide-react'
import { useState } from 'react'

import { ApiError } from '../api/client'
import {
  acceptExternalAiConsent,
  deleteAiProviderKey,
  getAiProviderStatus,
  saveAiProviderKey,
  setAiGenerationMode,
  testAiProviderConnection,
  type GenerationMode,
} from '../api/aiProvider'

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

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [confirmTransfer, setConfirmTransfer] = useState(false)
  const [consentChecked, setConsentChecked] = useState(false)
  const query = useQuery({ queryKey: ['ai-provider'], queryFn: ({ signal }) => getAiProviderStatus(signal) })
  const status = query.data

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

  const busy = saveMutation.isPending || deleteMutation.isPending || testMutation.isPending || consentMutation.isPending || modeMutation.isPending
  const generationMode = status?.generation_mode ?? 'mock'
  const canTest = Boolean(status?.configured && status.credential_store.available && confirmTransfer && !busy)

  if (query.isLoading) {
    return <section className="settings-page"><div className="settings-loading"><LoaderCircle className="spin" size={18} aria-hidden="true" />正在读取 AI 服务状态</div></section>
  }

  if (query.isError || !status) {
    return <section className="settings-page"><div className="settings-error" role="alert"><CircleAlert size={18} aria-hidden="true" /><span>{errorText(query.error)}</span><button className="quiet-button" type="button" onClick={() => void query.refetch()}>重新读取</button></div></section>
  }

  return (
    <section className="settings-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">本机运行配置</span>
          <h1>设置</h1>
          <p>管理 AI 服务凭据和外发说明。Key 只保存在 Windows 凭据管理器中。</p>
        </div>
      </div>

      <div className="settings-grid">
        <section className="settings-section" aria-labelledby="ai-provider-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon"><KeyRound size={18} aria-hidden="true" /></span>
              <h2 id="ai-provider-heading">AI 服务配置</h2>
              <p>当前固定使用 DeepSeek，模型别名为 <code>{status.requested_model}</code>。</p>
            </div>
            <span className={`settings-state ${status.configured ? 'settings-state--ready' : ''}`}>
              {status.configured ? <Check size={14} aria-hidden="true" /> : <CircleAlert size={14} aria-hidden="true" />}
              {status.configured ? '已配置' : '未配置'}
            </span>
          </div>

          <div className="settings-provider-meta">
            <span>Provider：{status.display_name}</span>
            <span>存储：{status.credential_store.available ? 'Windows Credential Manager' : '不可用'}</span>
            <span>生成模式：{generationMode === 'deepseek' ? 'DeepSeek 在线' : 'Mock'}</span>
          </div>
          <div className="settings-mode-actions">
            <button className="quiet-button" type="button" disabled={busy || generationMode === 'mock'} onClick={() => modeMutation.mutate('mock')}>使用 Mock（无费用）</button>
            <button className="quiet-button" type="button" disabled={busy || generationMode === 'deepseek'} onClick={() => modeMutation.mutate('deepseek')}>使用 DeepSeek 在线生成</button>
          </div>
          {generationMode === 'deepseek' ? (
            <div className="settings-privacy-copy">
              <p>DeepSeek 在线生成、会外发当前问题与必要的少量证据。</p>
              {status.cost_estimate ? <p>{status.cost_estimate.disclaimer} 知识库问题按本地上限粗估不超过 {status.cost_estimate.knowledge_question_estimated_usd_ceiling} 美元；连接探测粗估不超过 {status.cost_estimate.probe_estimated_usd_ceiling} 美元。假设：{status.cost_estimate.rate_assumption}。</p> : null}
            </div>
          ) : <p className="settings-hint">当前是 Mock。启动、刷新和发送都不会调用 DeepSeek，也不会产生费用。</p>}
          {modeMutation.isError && <p className="settings-error-text" role="alert">{errorText(modeMutation.error)}</p>}

          <form className="settings-key-form" onSubmit={(event) => { event.preventDefault(); if (apiKey.trim()) saveMutation.mutate(apiKey.trim()) }}>
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
              <button className="icon-button icon-button--small" type="button" onClick={() => setShowKey((value) => !value)} aria-label={showKey ? '隐藏 API Key' : '显示 API Key'} title={showKey ? '隐藏 API Key' : '显示 API Key'}>
                {showKey ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
              </button>
            </div>
            <p className="settings-hint">保存后输入框会清空，页面不会读取或回显已保存的完整 Key。</p>
            {saveMutation.isError && <p className="settings-error-text" role="alert">{errorText(saveMutation.error)}</p>}
            <div className="settings-actions">
              <button className="primary-button" type="submit" disabled={!apiKey.trim() || busy}><KeyRound size={15} aria-hidden="true" />{saveMutation.isPending ? '正在保存' : '保存 Key'}</button>
              <button className="danger-button" type="button" disabled={!status.configured || busy} onClick={() => deleteMutation.mutate()}><Trash2 size={15} aria-hidden="true" />{deleteMutation.isPending ? '正在删除' : '删除本地 Key'}</button>
            </div>
          </form>

          <div className="settings-links">
            <a href={status.source_url} target="_blank" rel="noreferrer"><ExternalLink size={14} aria-hidden="true" />获取 API Key</a>
            <a href={status.pricing_url} target="_blank" rel="noreferrer"><ExternalLink size={14} aria-hidden="true" />查看官方价格</a>
          </div>
        </section>

        <section className="settings-section" aria-labelledby="external-ai-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon settings-icon--safe"><ShieldCheck size={18} aria-hidden="true" /></span>
              <h2 id="external-ai-heading">数据外发说明</h2>
              <p>连接测试和未来 AI 生成都需要明确确认外部 Provider 边界。</p>
            </div>
            <span className={`settings-state ${status.consent.accepted ? 'settings-state--ready' : ''}`}>{status.consent.accepted ? '已记录' : '待确认'}</span>
          </div>
          <div className="settings-privacy-copy">
            <p>未来启用 AI 生成时，只会发送当前问题、必要上下文和选中的少量证据。</p>
            <p>不会发送整库、原文件、Embedding、向量、数据库、日志或本地绝对路径。API Key 保存在本机系统凭据中。</p>
            <p>DeepSeek 按实际输入和输出 Token 计费；连接测试只发送固定短文本，也会产生极小 API 用量。</p>
          </div>
          {!status.consent.accepted && (
            <label className="settings-checkline">
              <input type="checkbox" checked={consentChecked} onChange={(event) => setConsentChecked(event.target.checked)} />
              <span>我已阅读本版本外发说明，并同意未来 AI 功能按上述范围发送必要文本。</span>
            </label>
          )}
          {!status.consent.accepted && <button className="quiet-button" type="button" disabled={!consentChecked || busy} onClick={() => consentMutation.mutate(status.consent.current_version)}>{consentMutation.isPending ? '正在记录' : '确认并记录说明版本'}</button>}
          {consentMutation.isError && <p className="settings-error-text" role="alert">{errorText(consentMutation.error)}</p>}
          {status.consent.accepted && <p className="settings-success-text"><Check size={14} aria-hidden="true" />已记录版本 {status.consent.version}，时间 {formatTime(status.consent.accepted_at)}</p>}
        </section>

        <section className="settings-section settings-section--probe" aria-labelledby="probe-heading">
          <div className="settings-section__heading">
            <div>
              <span className="settings-icon"><Wifi size={18} aria-hidden="true" /></span>
              <h2 id="probe-heading">连接探测</h2>
              <p>只在你主动点击并确认外发后发送固定短文本，不会带入文件或会话内容。</p>
            </div>
            {status.probe && <span className={`settings-state ${status.probe.status === 'success' ? 'settings-state--ready' : 'settings-state--error'}`}>{status.probe.status === 'success' ? '成功' : '失败'}</span>}
          </div>
          <label className="settings-checkline settings-checkline--probe">
            <input type="checkbox" checked={confirmTransfer} onChange={(event) => setConfirmTransfer(event.target.checked)} />
            <span>我确认本次会向 DeepSeek 发送固定测试文本，并接受极小 API 用量。</span>
          </label>
          <button className="primary-button" type="button" disabled={!canTest} onClick={() => testMutation.mutate()}><Wifi size={15} aria-hidden="true" />{testMutation.isPending ? '正在测试连接' : '测试连接'}</button>
          {testMutation.isError && <p className="settings-error-text" role="alert">{errorText(testMutation.error)}</p>}
          {status.probe && <div className={`settings-probe-result ${status.probe.status === 'success' ? 'settings-probe-result--success' : 'settings-probe-result--failure'}`}>
            <div><span>最近检查</span><strong>{formatTime(status.probe.checked_at)}</strong></div>
            <div><span>请求别名</span><strong>{status.probe.requested_model}</strong></div>
            <div><span>实际模型</span><strong>{status.probe.resolved_model ?? '未返回'}</strong></div>
            <div><span>流式能力</span><Capability value={status.probe.stream_supported} /></div>
            <div><span>Usage 字段</span><Capability value={status.probe.usage_supported} /></div>
            <div><span>本次 Token</span><strong>{status.probe.usage ? `输入 ${status.probe.usage.prompt_tokens ?? 0} · 输出 ${status.probe.usage.completion_tokens ?? 0}` : '未返回'}</strong></div>
            {status.probe.error_detail && <p>{status.probe.error_detail}</p>}
          </div>}
          {status.probe?.status === 'success' && <p className="settings-hint">探测成功只说明这次请求可用，不代表账户余额充足，也不代表正式聊天已经开启。</p>}
        </section>
      </div>
    </section>
  )
}
