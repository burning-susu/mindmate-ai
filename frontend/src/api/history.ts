import type { components } from './generated/openapi'
import { apiRequest } from './client'

export type ConversationHistoryItem = components['ConversationHistoryItem']
export type LearningHistoryItem = components['LearningHistoryItem']
export type HistoryTrashItem = components['HistoryTrashItem']

export type HistoryFilters = {
  q?: string
  mode?: string
  goalType?: string
  status?: string
  sourceStatus?: string
  dateFrom?: string
  dateTo?: string
}

function historyParams(cursor: string | undefined, limit: number, filters: HistoryFilters, goal = false) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  if (filters.q) params.set('q', filters.q)
  if (filters.mode) params.set('mode', filters.mode)
  if (goal && filters.goalType) params.set('goal_type', filters.goalType)
  if (filters.status) params.set('status', filters.status)
  if (filters.sourceStatus) params.set('source_status', filters.sourceStatus)
  if (filters.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters.dateTo) params.set('date_to', filters.dateTo)
  return params
}

export async function listConversationHistory(
  cursor?: string,
  limit = 30,
  filters: HistoryFilters = {},
  init?: RequestInit,
): Promise<{
  items: ConversationHistoryItem[]
  next_cursor?: string | null
  search_index_status?: string
}> {
  const params = historyParams(cursor, limit, filters)
  return apiRequest(`/api/v1/history/conversations?${params}`, init)
}

export async function listLearningHistory(
  cursor?: string,
  limit = 30,
  filters: HistoryFilters = {},
  init?: RequestInit,
): Promise<{
  items: LearningHistoryItem[]
  next_cursor?: string | null
  search_index_status?: string
}> {
  const params = historyParams(cursor, limit, filters, true)
  return apiRequest(`/api/v1/history/learning-sessions?${params}`, init)
}

export async function listHistoryTrash(
  objectType: 'conversation' | 'learning_session',
  cursor?: string,
  limit = 30,
  init?: RequestInit,
): Promise<{ items: HistoryTrashItem[]; next_cursor?: string | null }> {
  const params = new URLSearchParams({ object_type: objectType, limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  return apiRequest(`/api/v1/history/trash?${params}`, init)
}

export async function trashConversation(conversationId: string, expectedVersion: number) {
  const params = new URLSearchParams({ expected_version: String(expectedVersion) })
  return apiRequest<{ conversation_id: string; title: string; deleted_at: string | null; row_version: number }>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}?${params}`,
    { method: 'DELETE' },
  )
}

export async function restoreConversation(conversationId: string, expectedVersion: number) {
  const params = new URLSearchParams({ expected_version: String(expectedVersion) })
  return apiRequest<{ conversation_id: string; title: string; deleted_at: string | null; row_version: number }>(
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/restore?${params}`,
    { method: 'POST' },
  )
}

export async function trashLearningSession(learningSessionId: string, expectedVersion: number) {
  const params = new URLSearchParams({ expected_version: String(expectedVersion) })
  return apiRequest<{ learning_session_id: string; topic: string; deleted_at: string | null; row_version: number }>(
    `/api/v1/learning-sessions/${encodeURIComponent(learningSessionId)}?${params}`,
    { method: 'DELETE' },
  )
}

export async function restoreLearningSession(learningSessionId: string, expectedVersion: number) {
  const params = new URLSearchParams({ expected_version: String(expectedVersion) })
  return apiRequest<{ learning_session_id: string; topic: string; deleted_at: string | null; row_version: number }>(
    `/api/v1/learning-sessions/${encodeURIComponent(learningSessionId)}/restore?${params}`,
    { method: 'POST' },
  )
}
