import type { components } from './generated/openapi'
import { apiRequest } from './client'

export type HomeOverview = components['HomeOverviewResponse']
export type HomeTaskItem = components['HomeTaskItemResponse']

export type TaskRetentionPreview = {
  as_of: string
  eligible_total: number
  skipped_referenced: number
  success_or_cancelled: number
  failed_partial_interrupted: number
  active_not_eligible: number
  missing_completed_at: number
}

export type TaskRetentionRun = {
  as_of: string
  scanned: number
  purged: number
  skipped_referenced: number
  skipped_not_due: number
  skipped_active: number
  errors: number
  error_codes: string[]
}

export function getHomeOverview(taskLimit = 8): Promise<HomeOverview> {
  const params = new URLSearchParams({ task_limit: String(taskLimit) })
  return apiRequest(`/api/v1/home/overview?${params}`)
}

export function getTaskRetentionPreview(): Promise<TaskRetentionPreview> {
  return apiRequest('/api/v1/home/tasks/retention-preview')
}

export function purgeTaskRetention(body: {
  confirmed: boolean
  limit?: number
  clear_success?: boolean
  clear_cancelled?: boolean
  clear_failed?: boolean
}): Promise<TaskRetentionRun> {
  return apiRequest('/api/v1/home/tasks/retention-purge', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
