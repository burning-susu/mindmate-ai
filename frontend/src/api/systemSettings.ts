import { v7 as uuidv7 } from 'uuid'

import { ApiError, ensureLocalSession, apiRequest, type ProblemDetail } from './client'

export type StorageCategory = {
  key: string
  label: string
  byte_size: number | null
  available: boolean
  message: string | null
}

export type StorageOverview = {
  data_dir_configured: boolean
  data_dir_display: string
  database: string
  writable: boolean
  categories: StorageCategory[]
  total_byte_size: number | null
  readable: boolean
  message: string | null
}

export type UsageBucket = {
  operations: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  unknown_usage_operations: number
  estimated_usd: string | null
  usage_complete: boolean
}

export type AiUsageSummary = {
  period_days: number
  since: string
  until: string
  currency: string
  totals: { mock: UsageBucket; online: UsageBucket }
  daily: Array<{ date: string; mock: UsageBucket; online: UsageBucket }>
  by_model: Array<{ channel: string; model: string } & UsageBucket>
  by_provider?: Array<{ provider: string } & UsageBucket>
  online_actual_usage_available: boolean
  online_actual_usage_message: string | null
  unknown_usage_operations: number
  estimated_online_usd: string | null
  estimate_disclaimer: string
  cost_estimate: {
    checked_on: string
    pricing_url: string
    rate_assumption: string
    input_usd_per_million_tokens: string
    output_usd_per_million_tokens: string
    disclaimer: string
  }
}

export type BudgetConfig = {
  enabled: boolean
  currency: string
  period: '30d' | 'calendar_month' | string
  hard_stop_usd: string | null
  soft_remind_usd: string | null
  unknown_usage_policy: 'deny' | 'confirm'
  updated_at: string | null
}

export type BudgetStatus = {
  budget: BudgetConfig
  usage_summary: {
    estimated_online_usd: string | null
    unknown_usage_operations: number
    online_operations: number
    online_usage_complete: boolean
    online_actual_usage_message: string | null
  }
  spent_estimated_usd: string
  remaining_estimated_usd: string | null
  soft_remind_triggered: boolean
  hard_stop_would_block: boolean
  currency: string
  estimate_disclaimer: string
}

export type PrivacyStatus = {
  log_retention: {
    available: boolean
    message: string
    retention_days: number
    max_bytes: number
    file_count: number
    bytes_used: number
    cleanup_complete: boolean
  }
  diagnostics_export: { available: boolean; message: string }
  storage_migration: { available: boolean; message: string }
  secrets_policy: {
    api_key_in_sqlite: boolean
    api_key_in_backup: boolean
    message: string
  }
}

export type DiagnosticsTask = {
  diagnostic_id: string
  task_type: string
  status: string
  phase: string | null
  progress: number | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  error_code: string | null
}

export type DiagnosticsProjection = {
  schema_version: string
  included_categories: string[]
  excluded_categories: string[]
  application: {
    version: string
    runtime: string
    platform: string
    platform_release: string
    architecture: string
    python_version: string
  }
  configuration: {
    provider_mode: string
    provider_model: string
    data_directory_configured: boolean
  }
  storage: {
    database: string
    database_present: boolean
    database_readable: boolean
    data_directory_writable: boolean
  }
  tasks: {
    total_count: number
    status_counts: Record<string, number>
    recent_count: number
    truncated: boolean
    time_range: { from: string | null; to: string | null }
    items: DiagnosticsTask[]
  }
  privacy: {
    local_only: boolean
    auto_upload: boolean
    notice: string
  }
}

export type DiagnosticsPreview = {
  schema_version: string
  generated_at: string
  estimated_size_bytes: number
  included_categories: string[]
  excluded_categories: string[]
  time_range: { from: string | null; to: string | null }
  task_summary: {
    total_count: number
    recent_count: number
    truncated: boolean
    status_counts: Record<string, number>
  }
  projection: DiagnosticsProjection
}

export function getStorageOverview(signal?: AbortSignal) {
  return apiRequest<StorageOverview>('/api/v1/system/storage', { signal })
}

export function getAiUsageSummary(signal?: AbortSignal) {
  return apiRequest<AiUsageSummary>('/api/v1/system/ai-usage', { signal })
}

export function getAiBudgetStatus(signal?: AbortSignal) {
  return apiRequest<BudgetStatus>('/api/v1/system/ai-budget', { signal })
}

export function updateAiBudget(payload: {
  enabled: boolean
  hard_stop_usd?: string | null
  soft_remind_usd?: string | null
  period?: '30d' | 'calendar_month'
  unknown_usage_policy?: 'deny' | 'confirm'
}) {
  return apiRequest<BudgetStatus>('/api/v1/system/ai-budget', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function getPrivacyStatus(signal?: AbortSignal) {
  return apiRequest<PrivacyStatus>('/api/v1/system/privacy', { signal })
}

export type DiagnosticLogClearResult = {
  files_removed: number
  bytes_removed: number
  remaining_files: number
  remaining_bytes: number
  complete: boolean
}

export function clearDiagnosticLogs() {
  return apiRequest<DiagnosticLogClearResult>('/api/v1/system/diagnostics/logs/clear', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function getDiagnosticsPreview(signal?: AbortSignal) {
  return apiRequest<DiagnosticsPreview>('/api/v1/system/diagnostics/preview', { signal })
}

export async function downloadDiagnostics(filenameHint = 'mindmate-diagnostics.json') {
  await ensureLocalSession()
  const response = await fetch('/api/v1/system/diagnostics/export', {
    method: 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'X-Request-ID': uuidv7() },
  })
  if (!response.ok) {
    let problem: ProblemDetail
    try {
      problem = (await response.json()) as ProblemDetail
    } catch {
      throw new Error('导出诊断包失败，请重试。')
    }
    throw new ApiError(response.status, problem)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition)
  const rawName = match?.[1] || match?.[2]
  const filename = rawName ? decodeURIComponent(rawName) : filenameHint
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function formatBytes(value: number | null | undefined) {
  if (value == null) return '暂时无法读取'
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value
  let unit = -1
  do {
    size /= 1024
    unit += 1
  } while (size >= 1024 && unit < units.length - 1)
  return `${size.toFixed(size >= 10 || unit === 0 ? 1 : 2)} ${units[unit]}`
}
