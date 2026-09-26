import type { components } from './generated/openapi'
import { apiRequest } from './client'

export type HomeOverview = components['HomeOverviewResponse']
export type HomeTaskItem = components['HomeTaskItemResponse']

export function getHomeOverview(taskLimit = 8): Promise<HomeOverview> {
  const params = new URLSearchParams({ task_limit: String(taskLimit) })
  return apiRequest(`/api/v1/home/overview?${params}`)
}
