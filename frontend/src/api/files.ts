import type { components } from './generated/openapi'
import { ApiError, apiRequest, apiUpload } from './client'

export type FileItem = components['FileItemResponse']
export type FileListResponse = components['FileListResponse']
export type FolderItem = components['FolderResponse']
export type FolderListResponse = components['FolderListResponse']
export type TagItem = components['TagResponse']
export type TagListResponse = components['TagListResponse']
export type TrashResponse = components['TrashResponse']
export type TrashFolderItem = components['TrashFolderResponse']

export type FileImportItem = {
  item_index: number
  original_name: string
  status: string
  hash_status?: string | null
  duplicate_status: string
  file_id?: string | null
  task_id?: string | null
  error?: string | null
  error_code?: string
  parse_status?: string | null
  parse_error?: string | null
  parse_failure_stage?: string | null
  parse_error_id?: string | null
  parse_retry_count?: number | null
}

export type FileImportResponse = {
  import_id: string
  task_id: string
  status: string
  phase?: string | null
  progress?: number | null
  items: FileImportItem[]
  folder_id?: string | null
  tag_ids?: string[]
  knowledge_base_id?: string | null
  error?: string | null
  cancel_reason_code?: string | null
}

export function importFiles(
  files: File[],
  fields: Record<string, string | undefined> = {},
  idempotencyKey?: string,
): Promise<FileImportResponse> {
  return apiUpload<FileImportResponse>('/api/v1/file-imports', files, fields, idempotencyKey)
}

export function decideFileImportDuplicates(
  importId: string,
  decisions: Array<{ item_index: number; decision: 'REUSE_EXISTING' | 'CREATE_SEPARATE_RECORD' | 'SKIP' }>,
  idempotencyKey?: string,
): Promise<FileImportResponse> {
  return apiRequest(`/api/v1/file-imports/${importId}/duplicate-decisions`, {
    method: 'POST',
    headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined,
    body: JSON.stringify({ decisions }),
  })
}

export function listRecentFiles(limit = 5): Promise<FileListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    sort: 'updated_at',
  })
  return apiRequest(`/api/v1/files?${params}`)
}

export function isVersionConflict(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 412
}

export function updateFolder(
  folderId: string,
  rowVersion: number,
  name: string,
): Promise<FolderItem> {
  return apiRequest(`/api/v1/folders/${folderId}`, {
    method: 'PATCH',
    body: JSON.stringify({ name, row_version: rowVersion }),
  })
}

export function moveFolder(
  folderId: string,
  rowVersion: number,
  parentFolderId: string | null,
): Promise<FolderItem> {
  return apiRequest(`/api/v1/folders/${folderId}/move`, {
    method: 'POST',
    body: JSON.stringify({ parent_folder_id: parentFolderId, row_version: rowVersion }),
  })
}

export function deleteFolder(
  folder: FolderItem,
  strategy: 'MOVE_CHILDREN' | 'TRASH_RECURSIVE',
): Promise<{ folder_id: string; status: string; row_version: number }> {
  const params = new URLSearchParams({
    deletion_strategy: strategy,
    expected_version: String(folder.row_version),
  })
  return apiRequest(`/api/v1/folders/${folder.folder_id}?${params}`, { method: 'DELETE' })
}

export function updateTag(
  tagId: string,
  rowVersion: number,
  patch: { name?: string; color?: string | null },
): Promise<TagItem> {
  return apiRequest(`/api/v1/tags/${tagId}`, {
    method: 'PATCH',
    body: JSON.stringify({ ...patch, row_version: rowVersion }),
  })
}

export function deleteTag(
  tag: TagItem,
): Promise<{ tag_id: string; status: string; row_version: number }> {
  return apiRequest(
    `/api/v1/tags/${tag.tag_id}?expected_version=${encodeURIComponent(tag.row_version)}`,
    { method: 'DELETE' },
  )
}

export function restoreTrashObject<T>(
  objectType: 'file' | 'folder',
  objectId: string,
  rowVersion: number,
): Promise<T> {
  return apiRequest(
    `/api/v1/trash/${objectType}/${objectId}/restore?expected_version=${encodeURIComponent(rowVersion)}`,
    { method: 'POST' },
  )
}

export function purgeTrashObject(
  objectType: 'file' | 'folder',
  objectId: string,
  rowVersion: number,
): Promise<{ status: string }> {
  const params = new URLSearchParams({
    confirmed: 'true',
    expected_version: String(rowVersion),
  })
  return apiRequest(`/api/v1/trash/${objectType}/${objectId}?${params}`, { method: 'DELETE' })
}
