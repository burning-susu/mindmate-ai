import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert } from 'lucide-react'
import { useRef, useState } from 'react'
import { v7 as uuidv7 } from 'uuid'

import {
  acknowledgeRestoreProvider,
  cancelRestore,
  executeRestore,
  getRestoreStatus,
  precheckRestore,
  uploadRestoreArchive,
  type RestoreStatus,
} from '../api/backups'
import { ApiError } from '../api/client'
import { formatBytes } from '../api/systemSettings'

function phaseLabel(phase: string) {
  switch (phase) {
    case 'PRECHECKED':
      return '预检通过，等待确认'
    case 'RESTART_REQUIRED':
      return '已确认，等待重启后切换'
    case 'APPLYING':
      return '正在切换'
    case 'SUCCEEDED':
      return '恢复完成'
    case 'ROLLED_BACK':
      return '已回到恢复前的数据'
    case 'FAILED':
      return '恢复失败'
    case 'CANCELLED':
      return '已取消'
    case 'PRECHECK_EXPIRED':
      return '预检已过期'
    default:
      return '尚未开始恢复'
  }
}

export function BackupRestorePanel({ enabled }: { enabled: boolean }) {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const confirmKey = useRef(uuidv7())
  const [understood, setUnderstood] = useState(false)
  const [phrase, setPhrase] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const statusQuery = useQuery({
    queryKey: ['backup-restore-status'],
    queryFn: ({ signal }) => getRestoreStatus(signal),
    enabled,
    refetchInterval: (query) => {
      const phase = query.state.data?.phase
      return phase === 'RESTART_REQUIRED' || phase === 'APPLYING' ? 2000 : false
    },
  })

  const status = statusQuery.data
  const requiredPhrase = status?.confirm_phrase || '覆盖当前全部本地数据'
  const summary = status?.summary
  const canConfirm =
    status?.phase === 'PRECHECKED' &&
    summary?.executable === true &&
    understood &&
    phrase === requiredPhrase &&
    !status.writes_frozen

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const uploaded = await uploadRestoreArchive(file)
      return precheckRestore(uploaded.upload_id)
    },
    onSuccess: async (next) => {
      setUnderstood(false)
      setPhrase('')
      confirmKey.current = uuidv7()
      setError(null)
      setMessage(next.summary?.executable ? '预检完成。确认前不会改动当前数据。' : '预检未通过，当前数据未改动。')
      queryClient.setQueryData(['backup-restore-status'], next)
    },
    onError: (reason: unknown) => {
      setMessage(null)
      setError(reason instanceof ApiError ? reason.message : '预检失败，当前数据未改动。')
    },
  })

  const executeMutation = useMutation({
    mutationFn: (current: RestoreStatus) =>
      executeRestore(String(current.precheck_id), requiredPhrase, confirmKey.current),
    onSuccess: (next) => {
      setError(null)
      setMessage('恢复已确认。请完全退出并重新打开 MindMate，重启后才会切换数据。')
      queryClient.setQueryData(['backup-restore-status'], next)
    },
    onError: (reason: unknown) => {
      setMessage(null)
      setError(reason instanceof ApiError ? reason.message : '确认失败，当前数据未切换。')
    },
  })

  const cancelMutation = useMutation({
    mutationFn: cancelRestore,
    onSuccess: (next) => {
      setError(null)
      setMessage('已取消。若刚刚确认过恢复，请重启应用以恢复后台任务。')
      queryClient.setQueryData(['backup-restore-status'], next)
    },
    onError: (reason: unknown) => setError(reason instanceof ApiError ? reason.message : '取消失败。'),
  })

  const reconfirmMutation = useMutation({
    mutationFn: acknowledgeRestoreProvider,
    onSuccess: (next) => {
      setError(null)
      setMessage('已记录重新配置确认。当前仍是 Mock，不会自动外发。')
      queryClient.setQueryData(['backup-restore-status'], next)
      void queryClient.invalidateQueries({ queryKey: ['ai-provider-status'] })
    },
    onError: (reason: unknown) => setError(reason instanceof ApiError ? reason.message : '确认失败。'),
  })

  if (!enabled) {
    return (
      <p className="settings-hint">恢复入口保持禁用，直到恢复流程完成独立校验。</p>
    )
  }

  return (
    <div className="settings-restore">
      <p className="settings-hint">
        恢复会整份覆盖当前本地资料、知识库、对话和学习记录，不会合并。备份不含密钥、向量和模型。切换发生在你重启应用之后；失败会回到旧数据。
      </p>
      {statusQuery.isError && <p className="settings-error-text">暂时无法读取恢复状态。</p>}
      {status && (
        <p className="settings-restore__phase" role="status">
          {phaseLabel(status.phase)}
          {status.recovery_point_available ? ' · 本机已保留恢复点' : ''}
        </p>
      )}
      {summary && (
        <div className="settings-privacy-copy settings-backup-warning" role="note">
          <p>
            <strong>将被整份覆盖：</strong>
            {summary.overwrite_scope}
          </p>
          <p>
            包内 {summary.file_count ?? 0} 个文件 · {formatBytes(summary.total_size ?? 0)} · 格式{' '}
            {summary.backup_format_version} · 数据库 {summary.schema_plan === 'upgrade' ? '恢复时迁移' : '版本匹配'}
          </p>
          {summary.warnings?.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
          <p>索引在重建并校验前不可检索。恢复后需要重新确认 Provider，默认保持 Mock。</p>
        </div>
      )}
      {status?.restart_required && (
        <p className="settings-error-text" role="alert">
          请完全退出并重新打开 MindMate。重启前取消不会覆盖数据；不要重复选择另一份备份。
        </p>
      )}
      {status?.phase === 'SUCCEEDED' && (
        <p role="status">恢复已完成。旧数据保留在本机恢复点。全文和向量索引需要重建后才能检索。</p>
      )}
      {(status?.phase === 'ROLLED_BACK' || status?.phase === 'FAILED') && status.error_detail && (
        <p className="settings-error-text" role="alert">{status.error_detail}</p>
      )}
      <label className="settings-restore__file">
        选择备份包
        <input
          ref={fileRef}
          type="file"
          accept=".mindmate-backup,application/zip"
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (file) uploadMutation.mutate(file)
          }}
        />
      </label>
      {status?.phase === 'PRECHECKED' && summary?.executable && (
        <label className="settings-check">
          <input
            type="checkbox"
            checked={understood}
            onChange={(event) => setUnderstood(event.target.checked)}
          />
          我了解这将整份覆盖当前本地数据，而不是合并
        </label>
      )}
      {understood && (
        <label className="settings-restore__phrase">
          输入确认语：{requiredPhrase}
          <input
            value={phrase}
            onChange={(event) => setPhrase(event.target.value)}
            aria-label="恢复确认语"
          />
        </label>
      )}
      <div className="settings-actions">
        <button
          className="danger-button"
          type="button"
          disabled={!canConfirm || executeMutation.isPending}
          onClick={() => status && executeMutation.mutate(status)}
        >
          {executeMutation.isPending ? '正在确认…' : '确认恢复并准备重启'}
        </button>
        <button
          className="quiet-button"
          type="button"
          disabled={cancelMutation.isPending || !status || !['PRECHECKED', 'RESTART_REQUIRED', 'UPLOADED'].includes(status.phase)}
          onClick={() => cancelMutation.mutate()}
        >
          取消恢复
        </button>
        {status?.provider_reconfirm_required && (
          <button className="quiet-button" type="button" onClick={() => reconfirmMutation.mutate()}>
            我已核对，保持 Mock 不外发
          </button>
        )}
      </div>
      {message && <p role="status">{message}</p>}
      {error && (
        <p className="settings-error-text" role="alert">
          <CircleAlert size={14} aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  )
}
