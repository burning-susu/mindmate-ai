import type { components } from './generated/openapi'
import { apiRequest } from './client'

export type KnowledgeBaseItem = components['KnowledgeBaseResponse']
export type KnowledgeBaseListResponse = components['KnowledgeBaseListResponse']
export type KnowledgeBaseCreate = components['KnowledgeBaseCreate']
export type KnowledgeBaseMember = components['KnowledgeBaseMemberResponse']
export type KnowledgeBaseMemberList = components['KnowledgeBaseMemberListResponse']
export type KnowledgeMembershipTask = components['KnowledgeMembershipTaskResponse']
export type RetrievalTestRequest = components['RetrievalTestRequest']
export type RetrievalTestResponse = components['RetrievalTestResponse']
export type RetrievalTestCandidate = components['RetrievalTestCandidateResponse']
export type RetrievalTestLocation = components['RetrievalTestLocation']

export function createKnowledgeBase(payload: KnowledgeBaseCreate): Promise<KnowledgeBaseItem> {
  return apiRequest('/api/v1/knowledge-bases', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateKnowledgeBase(
  knowledgeBaseId: string,
  rowVersion: number,
  patch: Pick<KnowledgeBaseCreate, 'name' | 'description' | 'icon' | 'color'>,
): Promise<KnowledgeBaseItem> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}`, {
    method: 'PATCH',
    body: JSON.stringify({ ...patch, row_version: rowVersion }),
  })
}

export function trashKnowledgeBase(item: KnowledgeBaseItem): Promise<KnowledgeBaseItem> {
  return apiRequest(
    `/api/v1/knowledge-bases/${item.knowledge_base_id}?expected_version=${encodeURIComponent(item.row_version)}`,
    { method: 'DELETE' },
  )
}

export function restoreKnowledgeBase(item: KnowledgeBaseItem): Promise<KnowledgeBaseItem> {
  return apiRequest(
    `/api/v1/trash/knowledge-base/${item.knowledge_base_id}/restore?expected_version=${encodeURIComponent(item.row_version)}`,
    { method: 'POST' },
  )
}

export function purgeKnowledgeBase(item: KnowledgeBaseItem): Promise<{ status: string }> {
  const params = new URLSearchParams({
    confirmed: 'true',
    expected_version: String(item.row_version),
  })
  return apiRequest(`/api/v1/trash/knowledge-base/${item.knowledge_base_id}?${params}`, {
    method: 'DELETE',
  })
}

export function listKnowledgeBaseMembers(
  knowledgeBaseId: string,
): Promise<KnowledgeBaseMemberList> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/files`)
}

export function addKnowledgeBaseMembers(
  knowledgeBaseId: string,
  fileIds: string[],
): Promise<KnowledgeMembershipTask> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/files`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  })
}

export function removeKnowledgeBaseMember(
  knowledgeBaseId: string,
  fileId: string,
): Promise<{ knowledge_base_id: string; file_id: string; status: string }> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/files/${fileId}`, {
    method: 'DELETE',
  })
}

export function getKnowledgeMembershipTask(taskId: string): Promise<KnowledgeMembershipTask> {
  return apiRequest(`/api/v1/tasks/${taskId}`)
}

export function runKnowledgeBaseRetrievalTest(
  knowledgeBaseId: string,
  payload: RetrievalTestRequest,
  signal?: AbortSignal,
): Promise<RetrievalTestResponse> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/retrieval-tests`, {
    method: 'POST',
    body: JSON.stringify(payload),
    signal,
  })
}
