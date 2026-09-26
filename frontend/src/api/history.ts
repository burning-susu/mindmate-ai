import type { components } from './generated/openapi'
import { apiRequest } from './client'

export type ConversationHistoryItem = components['ConversationHistoryItem']
export type LearningHistoryItem = components['LearningHistoryItem']

export async function listConversationHistory(cursor?: string, limit = 30): Promise<{
  items: ConversationHistoryItem[]
  next_cursor?: string | null
}> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  return apiRequest(`/api/v1/history/conversations?${params}`)
}

export async function listLearningHistory(cursor?: string, limit = 30): Promise<{
  items: LearningHistoryItem[]
  next_cursor?: string | null
}> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)
  return apiRequest(`/api/v1/history/learning-sessions?${params}`)
}
