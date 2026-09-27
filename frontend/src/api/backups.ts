import { v7 as uuidv7 } from 'uuid'

import { ApiError, ensureLocalSession, apiRequest, type ProblemDetail } from './client'
import { formatBytes } from './systemSettings'

export type BackupScope = {
  database_snapshot: boolean
  content_objects: boolean
  parsed_artifacts: boolean
  non_secret_config: boolean
  vectors: boolean
  fts: boolean
  models: boolean
  logs: boolean
  secrets: boolean
}

export type BackupRecord = {
  backup_id: string
  status: 'CREATING' | 'COMPLETED' | 'FAILED' | string
  backup_format_version: string
  schema_version: string
  file_count: number
  total_size: number
  created_at: string
  completed_at: string | null
  error_summary: string | null
  includes_vectors: boolean
  includes_parsed: boolean
  includes_secrets: boolean
  encrypted: boolean
  contains_user_files_and_history: boolean
  unencrypted_warning: boolean
  warning_message: string
  download_available: boolean
  restore_available: boolean
  scope: BackupScope
}

export type BackupList = {
  items: BackupRecord[]
  restore_available: boolean
  warning_message: string
}

export function listBackups(signal?: AbortSignal) {
  return apiRequest<BackupList>('/api/v1/backups', { signal })
}

export function getBackup(backupId: string, signal?: AbortSignal) {
  return apiRequest<BackupRecord>(`/api/v1/backups/${backupId}`, { signal })
}

export function createBackup(idempotencyKey?: string) {
  const headers: HeadersInit = {}
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
  return apiRequest<BackupRecord>('/api/v1/backups', {
    method: 'POST',
    headers,
    body: '{}',
  })
}

export function verifyBackup(backupId: string) {
  return apiRequest<{
    backup_id: string
    verified: boolean
    file_count: number | null
    total_size: number | null
    schema_version: string | null
    includes_secrets: boolean
    includes_vectors: boolean
  }>(`/api/v1/backups/${backupId}/verify`, {
    method: 'POST',
    body: '{}',
  })
}

export async function downloadBackup(backupId: string, filenameHint?: string) {
  await ensureLocalSession()
  const response = await fetch(`/api/v1/backups/${backupId}/download`, {
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
      throw new Error('下载备份失败，请重试。')
    }
    throw new ApiError(response.status, problem)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disposition)
  const rawName = match?.[1] || match?.[2]
  const filename = rawName ? decodeURIComponent(rawName) : filenameHint || `mindmate-backup-${backupId}.mindmate-backup`
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

export function formatBackupSize(value: number) {
  return formatBytes(value)
}

export function isBackupInProgress(status: string) {
  return status === 'CREATING' || status === 'RUNNING' || status === 'QUEUED'
}
