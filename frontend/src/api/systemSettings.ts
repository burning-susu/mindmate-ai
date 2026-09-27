import { apiRequest } from './client'

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
  log_retention: { available: boolean; message: string }
  diagnostics_export: { available: boolean; message: string }
  storage_migration: { available: boolean; message: string }
  secrets_policy: {
    api_key_in_sqlite: boolean
    api_key_in_backup: boolean
    message: string
  }
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
