import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import App from '../App'
import { queryClient } from '../queryClient'

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  })
}

type FixtureProbe = {
  status: 'success' | 'failed'
  checked_at: string
  requested_model: string
  resolved_model: string | null
  stream_supported: string
  usage_supported: string
  structured_output_supported: string
  provider_request_id: string | null
  response_fingerprint: string | null
  usage: Record<string, number> | null
  error_code: string | null
  error_detail: string | null
  retryable: boolean | null
}

type FixtureStatus = {
  provider: string
  display_name: string
  configured: boolean
  credential_store: { available: boolean; type: string; error_code: string | null }
  requested_model: string
  consent: { current_version: string; accepted: boolean; version: string | null; accepted_at: string | null }
  probe: FixtureProbe | null
  source_url: string
  pricing_url: string
  generation_mode?: 'mock' | 'deepseek'
  cost_estimate?: {
    disclaimer: string
    knowledge_question_estimated_usd_ceiling: string
    probe_estimated_usd_ceiling: string
    rate_assumption: string
  }
}

const initialStatus: FixtureStatus = {
  provider: 'DEEPSEEK',
  display_name: 'DeepSeek',
  configured: false,
  credential_store: { available: true, type: 'windows-credential-manager', error_code: null },
  requested_model: 'deepseek-flash',
  consent: { current_version: 'deepseek-external-ai-v1', accepted: false, version: null, accepted_at: null },
  probe: null,
  source_url: 'https://platform.deepseek.com/api_keys',
  pricing_url: 'https://api-docs.deepseek.com/quick_start/pricing',
}

function settingsAuxiliaryResponse(url: string, logFileCount = 1) {
  if (url.endsWith('/api/v1/system/storage')) {
    return response({
      data_dir_configured: true,
      data_dir_display: '%LOCALAPPDATA%\\MindMateAI',
      database: 'sqlite',
      writable: true,
      categories: [],
      total_byte_size: 0,
      readable: true,
      message: null,
    })
  }
  if (url.includes('/api/v1/system/ai-usage')) {
    const query = new URL(url, 'http://127.0.0.1').searchParams
    return response({
      period_days: 30,
      window_period: '30d',
      since: query.get('start') ?? '2026-08-28T00:00:00Z',
      until: query.get('end') ?? '2026-09-27T00:00:00Z',
      window_start: query.get('start') ?? '2026-08-28T00:00:00Z',
      window_end: query.get('end') ?? '2026-09-27T00:00:00Z',
      checked_at: '2026-09-28T10:00:00Z',
      currency: 'USD',
      totals: {
        mock: { operations: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, unknown_usage_operations: 0, unknown_price_operations: 0, estimated_usd: null, reserved_estimated_usd: '0', unknown_exposure_estimated_usd: '0', usage_complete: true },
        online: { operations: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, unknown_usage_operations: 0, unknown_price_operations: 0, estimated_usd: '0', reserved_estimated_usd: '0', unknown_exposure_estimated_usd: '0', usage_complete: true },
      },
      daily: [],
      by_model: [],
      by_provider: [],
      by_operation_type: [],
      online_actual_usage_available: false,
      online_actual_usage_message: '在线实际用量暂无记录',
      unknown_usage_operations: 0,
      estimated_online_usd: '0',
      reserved_online_usd: '0',
      unknown_exposure_estimated_usd: '0',
      budget_exposure_estimated_usd: '0',
      provider_billing_urls: { deepseek: 'https://platform.deepseek.com/usage', openai: 'https://platform.openai.com/usage' },
      used_price_sources: [],
      billing_reconciliation_status: '尚未与官方账单核对',
      estimate_disclaimer: '估算说明',
      cost_estimate: { checked_on: '2026-09-26', pricing_url: 'https://example.invalid', rate_assumption: 'fixture', input_usd_per_million_tokens: '0.30', output_usd_per_million_tokens: '1.20', disclaimer: '估算说明' },
      cost_estimates: {
        deepseek: { checked_on: '2026-09-26', pricing_url: 'https://example.invalid/deepseek', rate_assumption: 'fixture', input_usd_per_million_tokens: '0.30', output_usd_per_million_tokens: '1.20', disclaimer: '估算说明' },
        openai: { checked_on: '2026-09-27', pricing_url: 'https://example.invalid/openai', rate_assumption: 'fixture', input_usd_per_million_tokens: '2', output_usd_per_million_tokens: '10', disclaimer: '估算说明' },
      },
    })
  }
  if (url.endsWith('/api/v1/system/ai-budget')) {
    return response({
      budget: { enabled: false, currency: 'USD', period: '30d', hard_stop_usd: null, soft_remind_usd: null, unknown_usage_policy: 'deny', updated_at: null },
      usage_summary: { estimated_online_usd: '0', unknown_usage_operations: 0, online_operations: 0, online_usage_complete: true, online_actual_usage_message: '在线实际用量暂无记录' },
      spent_estimated_usd: '0',
      budget_exposure_estimated_usd: '0',
      remaining_estimated_usd: null,
      soft_remind_triggered: false,
      hard_stop_would_block: false,
      hard_stop_block_reason: null,
      checked_at: '2026-09-28T10:00:00Z',
      window_start: '2026-08-28T00:00:00Z',
      window_end: '2026-09-27T00:00:00Z',
      billing_reconciliation_status: '尚未与官方账单核对',
      currency: 'USD',
      estimate_disclaimer: '估算说明',
    })
  }
  if (url.endsWith('/api/v1/system/privacy')) {
    return response({
      log_retention: {
        available: true,
        message: '受控结构化应用事件：最多保留 30 天或 100 MB。',
        retention_days: 30,
        max_bytes: 100 * 1024 * 1024,
        file_count: logFileCount,
        bytes_used: logFileCount * 1024,
        cleanup_complete: true,
      },
      diagnostics_export: { available: true, message: '可预览并导出安全状态包；仅保存在本机，不自动上传。' },
      storage_migration: { available: false, message: '存储迁移尚未实现' },
      secrets_policy: { api_key_in_sqlite: false, api_key_in_backup: false, message: 'Key 仅存系统凭据' },
    })
  }
  if (url.endsWith('/api/v1/system/diagnostics/preview')) {
    return response({
      schema_version: 'mindmate-diagnostics.v1',
      generated_at: '2026-09-28T10:00:00Z',
      estimated_size_bytes: 640,
      included_categories: ['应用版本与平台运行状态', '非秘密 Provider/模型配置状态'],
      excluded_categories: ['原始日志、数据库快照、备份、文件与解析正文'],
      time_range: { from: null, to: null },
      task_summary: { total_count: 0, recent_count: 0, truncated: false, status_counts: {} },
      projection: {
        schema_version: 'mindmate-diagnostics.v1',
        included_categories: ['应用版本与平台运行状态', '非秘密 Provider/模型配置状态'],
        excluded_categories: ['原始日志、数据库快照、备份、文件与解析正文'],
        application: { version: '0.1.0', runtime: 'local', platform: 'Windows', platform_release: '11', architecture: 'AMD64', python_version: '3.12.0' },
        configuration: { provider_mode: 'mock', provider_model: 'deepseek-flash', data_directory_configured: true },
        storage: { database: 'sqlite', database_present: true, database_readable: true, data_directory_writable: true },
        tasks: { total_count: 0, status_counts: {}, recent_count: 0, truncated: false, time_range: { from: null, to: null }, items: [] },
        privacy: { local_only: true, auto_upload: false, notice: '保存在本机，不自动上传。' },
      },
    })
  }
  if (url.endsWith('/api/v1/embedding-model')) {
    return response({
      state: 'MISSING',
      phase: null,
      base_model_id: 'BAAI/bge-small-zh-v1.5',
      base_model_url: 'https://example.invalid',
      artifact_repository_id: 'fixture',
      artifact_url: 'https://example.invalid',
      license: 'MIT',
      base_revision: 'fixture',
      artifact_revision: 'fixture',
      artifact_fingerprint: 'fixture',
      total_size_bytes: 0,
      downloaded_bytes: 0,
      current_file: null,
      file_downloaded_bytes: null,
      file_size_bytes: null,
      task_id: null,
      diagnostic_id: null,
      error_code: null,
      can_install: true,
      can_cancel: false,
    })
  }
  if (url.endsWith('/api/v1/backups') || url.includes('/api/v1/backups?')) {
    return response({ items: [], restore_available: false, warning_message: '备份未加密' })
  }
  return null
}

describe('stage 6 AI provider configuration', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('saves a key, clears the input, and requires explicit probe confirmation', async () => {
    window.history.pushState({}, '', '/settings')
    let currentStatus: FixtureStatus = structuredClone(initialStatus)
    const calls: Array<{ url: string; method?: string; body?: unknown }> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      const auxiliary = settingsAuxiliaryResponse(url)
      if (auxiliary) return auxiliary
      if (url.endsWith('/api/v1/ai/provider/key') && init?.method === 'POST') {
        calls.push({ url, method: init.method, body: JSON.parse(String(init.body)) })
        currentStatus = { ...currentStatus, configured: true }
        return response(currentStatus)
      }
      if (url.endsWith('/api/v1/ai/provider/test') && init?.method === 'POST') {
        calls.push({ url, method: init.method, body: JSON.parse(String(init.body)) })
        currentStatus = {
          ...currentStatus,
          probe: {
            status: 'success', checked_at: '2026-09-25T09:00:00Z', requested_model: 'deepseek-flash',
            resolved_model: 'deepseek-v4.1-flash', stream_supported: 'supported', usage_supported: 'supported',
            structured_output_supported: 'unknown', provider_request_id: 'probe', response_fingerprint: 'fingerprint',
            usage: { prompt_tokens: 8, completion_tokens: 3, total_tokens: 11 }, error_code: null, error_detail: null, retryable: null,
          },
        }
        return response(currentStatus)
      }
      if (url.endsWith('/api/v1/ai/provider')) return response(currentStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('heading', { name: '设置' })).toBeInTheDocument()
    const keyInput = screen.getByLabelText('DeepSeek API Key')
    fireEvent.change(keyInput, { target: { value: 'fixture-secret' } })
    fireEvent.click(screen.getByRole('button', { name: '保存 Key' }))
    await waitFor(() => expect(keyInput).toHaveValue(''))
    expect(calls[0]).toMatchObject({ body: { api_key: 'fixture-secret' } })
    expect(screen.getByText('已配置')).toBeInTheDocument()

    const testButton = screen.getByRole('button', { name: '测试连接' })
    expect(testButton).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /固定测试文本/ }))
    expect(testButton).toBeEnabled()
    fireEvent.click(testButton)
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/ai/provider/test'))).toBe(true))
    expect(calls.find((call) => call.url.endsWith('/ai/provider/test'))?.body).toEqual({ confirm_external_transfer: true })
    expect(await screen.findByText('deepseek-v4.1-flash')).toBeInTheDocument()
  })

  it('records external AI consent as a separate versioned action', async () => {
    window.history.pushState({}, '', '/settings')
    let currentStatus: FixtureStatus = structuredClone(initialStatus)
    let consentBody: unknown
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      const auxiliary = settingsAuxiliaryResponse(url)
      if (auxiliary) return auxiliary
      if (url.endsWith('/api/v1/ai/consent') && init?.method === 'POST') {
        consentBody = JSON.parse(String(init.body))
        currentStatus = {
          ...currentStatus,
          consent: { ...currentStatus.consent, accepted: true, version: 'deepseek-external-ai-v1', accepted_at: '2026-09-25T09:00:00Z' },
        }
        return response(currentStatus.consent)
      }
      if (url.endsWith('/api/v1/ai/provider')) return response(currentStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('待确认')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /未来 AI 功能/ }))
    fireEvent.click(screen.getByRole('button', { name: '确认并记录说明版本' }))
    await waitFor(() => expect(consentBody).toEqual({ version: 'deepseek-external-ai-v1' }))
    expect(await screen.findByText(/已记录版本 deepseek-external-ai-v1/)).toBeInTheDocument()
  })

  it('switches generation mode without sending a key or a provider request', async () => {
    window.history.pushState({}, '', '/settings')
    let currentStatus: FixtureStatus = structuredClone(initialStatus)
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      const auxiliary = settingsAuxiliaryResponse(url)
      if (auxiliary) return auxiliary
      if (url.endsWith('/api/v1/ai/provider/generation-mode') && init?.method === 'POST') {
        calls.push(String(init.body))
        currentStatus = { ...currentStatus, generation_mode: 'deepseek' }
        return response(currentStatus)
      }
      if (url.endsWith('/api/v1/ai/provider')) return response(currentStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: '使用 DeepSeek 在线生成' }))
    await waitFor(() => expect(calls).toEqual([JSON.stringify({ mode: 'deepseek' })]))
    expect(await screen.findByText('DeepSeek 在线生成、会外发当前问题与必要的少量证据。')).toBeInTheDocument()
    expect(calls.some((body) => body.includes('api_key'))).toBe(false)
  })

  it('queries a historical UTC usage window without changing the active budget period', async () => {
    queryClient.clear()
    window.history.pushState({}, '', '/settings')
    const usageRequests: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      const auxiliary = settingsAuxiliaryResponse(url)
      if (auxiliary) {
        if (url.includes('/api/v1/system/ai-usage')) usageRequests.push(url)
        return auxiliary
      }
      if (url.endsWith('/api/v1/ai/provider')) return response(initialStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('heading', { name: '设置' })).toBeInTheDocument()
    expect(screen.getByLabelText('预算周期')).toHaveValue('30d')
    fireEvent.click(screen.getByText('历史窗口'))
    fireEvent.change(screen.getByLabelText('开始日期（UTC）'), { target: { value: '2026-09-01' } })
    fireEvent.change(screen.getByLabelText('结束日期（UTC，不包含）'), { target: { value: '2026-10-01' } })
    fireEvent.click(screen.getByRole('button', { name: '查询历史窗口' }))

    expect(await screen.findByText(/UTC 窗口：2026-09-01T00:00:00Z 至 2026-10-01T00:00:00Z/)).toBeInTheDocument()
    expect(usageRequests).toHaveLength(2)
    const historyRequest = new URL(usageRequests[1], 'http://127.0.0.1')
    expect(historyRequest.searchParams.get('start')).toBe('2026-09-01T00:00:00Z')
    expect(historyRequest.searchParams.get('end')).toBe('2026-10-01T00:00:00Z')
    expect(screen.getByLabelText('预算周期')).toHaveValue('30d')
  })

  it('previews the safe diagnostics projection and lets the user cancel it', async () => {
    queryClient.clear()
    window.history.pushState({}, '', '/settings')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      const auxiliary = settingsAuxiliaryResponse(url)
      if (auxiliary) return auxiliary
      if (url.endsWith('/api/v1/ai/provider')) return response(initialStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    const preview = await screen.findByRole('button', { name: '预览诊断内容' })
    fireEvent.click(preview)
    expect(await screen.findByText(/包含：应用版本与平台运行状态；非秘密 Provider\/模型配置状态/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '取消预览' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '取消预览' }))
    await waitFor(() => expect(screen.queryByText(/包含：应用版本与平台运行状态/)).not.toBeInTheDocument())
  })

  it('requires confirmation before clearing local diagnostic logs and refreshes the count', async () => {
    queryClient.clear()
    window.history.pushState({}, '', '/settings')
    let logFileCount = 2
    const clearCalls: string[] = []
    vi.stubGlobal('confirm', vi.fn(() => false))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/system/diagnostics/logs/clear')) {
        clearCalls.push(String(init?.method))
        logFileCount = 0
        return response({
          files_removed: 2,
          bytes_removed: 2048,
          remaining_files: 0,
          remaining_bytes: 0,
          complete: true,
        })
      }
      const auxiliary = settingsAuxiliaryResponse(url, logFileCount)
      if (auxiliary) return auxiliary
      if (url.endsWith('/api/v1/ai/provider')) return response(initialStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    const clearButton = await screen.findByRole('button', { name: '清理可清理的诊断日志' })
    fireEvent.click(clearButton)
    expect(clearCalls).toEqual([])

    vi.mocked(window.confirm).mockReturnValue(true)
    fireEvent.click(clearButton)
    await waitFor(() => expect(clearCalls).toEqual(['POST']))
    expect(await screen.findByText('已清理 2 个诊断日志文件，释放 2.0 KB。')).toBeInTheDocument()
    expect(await screen.findByText(/当前 0 个文件 \/ 0 B/)).toBeInTheDocument()
  })

  it('shows a safe error when diagnostic log cleanup fails', async () => {
    queryClient.clear()
    window.history.pushState({}, '', '/settings')
    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/system/diagnostics/logs/clear')) {
        return response({
          type: 'about:blank', title: '系统设置失败', status: 503,
          code: 'LOG_CLEANUP_FAILED', detail: '诊断日志暂时无法清理，请稍后重试。',
          instance: url, request_id: 'request-safe-1', retryable: true,
          field_errors: [], actions: [],
        }, 503)
      }
      const auxiliary = settingsAuxiliaryResponse(url)
      if (auxiliary) return auxiliary
      if (url.endsWith('/api/v1/ai/provider')) return response(initialStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: '清理可清理的诊断日志' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('诊断日志暂时无法清理，请稍后重试。')
  })

  it('labels mock chat and blocks online send until the user confirms the estimate', async () => {
    queryClient.clear()
    window.history.pushState({}, '', '/chat')
    let mode: 'mock' | 'deepseek' = 'mock'
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/ai/provider')) {
        return response({
          ...initialStatus,
          generation_mode: mode,
          configured: true,
          consent: { ...initialStatus.consent, accepted: true, version: 'deepseek-external-ai-v1' },
          cost_estimate: {
            checked_on: '2026-09-26',
            model: 'deepseek-flash',
            pricing_url: initialStatus.pricing_url,
            rate_assumption: '高峰、缓存未命中',
            input_usd_per_million_tokens: '0.30',
            output_usd_per_million_tokens: '1.20',
            knowledge_input_token_cap: 2048,
            knowledge_output_token_cap: 256,
            knowledge_question_estimated_usd_ceiling: '0.001',
            probe_output_token_cap: 8,
            probe_estimated_usd_ceiling: '0.0001',
            disclaimer: '这是保守估算，不是严格美元限额。',
          },
        })
      }
      if (url.endsWith('/api/v1/conversations')) return response({ items: [] })
      return response({ status: 'ok', version: '0.1.0' })
    }))

    const view = render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('Mock 生成，不会外发，也不会产生 DeepSeek 费用。')).toBeInTheDocument()
    mode = 'deepseek'
    view.unmount()
    queryClient.clear()
    window.history.pushState({}, '', '/chat')
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('DeepSeek 在线生成、会外发当前问题与必要的少量证据。')).toBeInTheDocument()
    const send = screen.getByRole('button', { name: '发送' })
    expect(send).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /保守费用估算/ }))
    fireEvent.change(screen.getByLabelText('消息内容'), { target: { value: '短问题' } })
    expect(screen.getByRole('button', { name: '发送' })).toBeEnabled()
  })

  it('shows a retry action for a failed backup and refreshes the queued state', async () => {
    queryClient.clear()
    window.history.pushState({}, '', '/settings')
    const backup = {
      backup_id: 'backup-66',
      status: 'FAILED',
      backup_format_version: '1',
      schema_version: 'fixture',
      file_count: 0,
      total_size: 0,
      created_at: '2026-09-28T09:00:00Z',
      completed_at: '2026-09-28T09:01:00Z',
      error_summary: '备份创建失败，请稍后重试。',
      includes_vectors: false,
      includes_parsed: false,
      includes_secrets: false,
      encrypted: false,
      contains_user_files_and_history: true,
      unencrypted_warning: true,
      warning_message: '备份未加密',
      download_available: false,
      restore_available: true,
      scope: {
        database_snapshot: true,
        content_objects: true,
        parsed_artifacts: false,
        non_secret_config: true,
        vectors: false,
        fts: false,
        models: false,
        logs: false,
        secrets: false,
      },
    }
    let currentBackup = backup
    let retryKey = ''
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/backups') || url.includes('/api/v1/backups?')) {
        return response({ items: [currentBackup], restore_available: true, warning_message: '备份未加密' })
      }
      if (url.endsWith('/api/v1/backups/backup-66/retry') && init?.method === 'POST') {
        retryKey = new Headers(init.headers).get('Idempotency-Key') || ''
        currentBackup = { ...currentBackup, status: 'QUEUED' }
        return response(currentBackup, 202)
      }
      const auxiliary = settingsAuxiliaryResponse(url)
      if (auxiliary) return auxiliary
      if (url.endsWith('/api/v1/ai/provider')) return response(initialStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: '重试备份' }))
    await waitFor(() => expect(retryKey).toBeTruthy())
    expect(await screen.findAllByText('排队中')).toHaveLength(2)
    expect(screen.getByRole('button', { name: '下载备份包' })).toBeDisabled()
  })
})
