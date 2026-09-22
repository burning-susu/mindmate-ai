import type { components } from './generated/openapi'
import { ApiError, apiRequest } from './client'

export type FileItem = components['FileItemResponse']
export type FileListResponse = components['FileListResponse']
export type FolderItem = components['FolderResponse']
export type FolderListResponse = components['FolderListResponse']
export type TagItem = components['TagResponse']
export type TagListResponse = components['TagListResponse']
export type TrashResponse = components['TrashResponse']
export type TrashFolderItem = components['TrashFolderResponse']

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
