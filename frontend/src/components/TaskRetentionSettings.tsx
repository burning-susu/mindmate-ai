import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2, X } from 'lucide-react'
import { useState } from 'react'

import { getTaskRetentionPreview, purgeTaskRetention } from '../api/home'

export default function TaskRetentionSettings() {
  const queryClient = useQueryClient()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [message, setMessage] = useState('')
  const preview = useQuery({
    queryKey: ['task-retention-preview'],
    queryFn: () => getTaskRetentionPreview(),
    retry: false,
  })
  const cleanup = useMutation({
    mutationFn: () => purgeTaskRetention({
      confirmed: true,
      clear_success: true,
      clear_cancelled: true,
      clear_failed: true,
      limit: 50,
    }),
    onSuccess: async (result) => {
      setConfirmOpen(false)
      setMessage(result.skipped_referenced > 0
        ? `已清理 ${result.purged} 条记录，${result.skipped_referenced} 条仍在使用的记录已保留。`
        : `已清理 ${result.purged} 条记录。`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['global-task-overview'] }),
        queryClient.invalidateQueries({ queryKey: ['home-overview'] }),
        queryClient.invalidateQueries({ queryKey: ['task-retention-preview'] }),
      ])
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : '清理失败，请稍后重试。'),
  })
  const eligible = preview.data?.eligible_total ?? 0

  return (
    <section className="settings-section settings-section--probe" aria-labelledby="task-records-heading">
      <div className="settings-section__heading">
        <div>
          <span className="settings-icon"><Trash2 size={18} aria-hidden="true" /></span>
          <h2 id="task-records-heading">任务记录</h2>
          <p>已到期的任务记录会自动清理，也可以在这里立即清理。</p>
        </div>
      </div>
      {preview.isPending ? <p className="settings-hint" role="status">正在读取任务记录</p> : null}
      {preview.isError ? (
        <div className="settings-error" role="alert">
          <span>任务记录暂时无法读取。</span>
          <button className="quiet-button" type="button" onClick={() => void preview.refetch()}>重新读取</button>
        </div>
      ) : null}
      {preview.data ? (
        <div className="task-retention-summary">
          <span>可清理 <strong>{eligible}</strong> 条</span>
          {preview.data.skipped_referenced > 0 ? <span>{preview.data.skipped_referenced} 条仍在使用</span> : null}
          <button className="quiet-button" type="button" disabled={eligible === 0 || cleanup.isPending} onClick={() => setConfirmOpen(true)}>
            清理已到期记录
          </button>
        </div>
      ) : null}
      {message ? <p className="settings-hint" role="status">{message}</p> : null}
      <Dialog.Root open={confirmOpen} onOpenChange={(open) => { if (!cleanup.isPending) setConfirmOpen(open) }}>
        <Dialog.Portal>
          <Dialog.Overlay className="history-dialog-overlay" />
          <Dialog.Content className="history-dialog" aria-describedby="task-retention-confirm-description">
            <div className="history-dialog__heading">
              <Dialog.Title className="history-dialog__title">清理任务记录</Dialog.Title>
              <Dialog.Close asChild>
                <button className="icon-button history-dialog__close" type="button" aria-label="关闭确认框" disabled={cleanup.isPending}><X size={16} /></button>
              </Dialog.Close>
            </div>
            <Dialog.Description id="task-retention-confirm-description" className="history-dialog__description">
              将清理 {eligible} 条已到期记录。活动任务和仍在使用的记录会保留。
            </Dialog.Description>
            <div className="history-dialog__actions">
              <Dialog.Close asChild><button className="quiet-button" type="button" disabled={cleanup.isPending}>取消</button></Dialog.Close>
              <button className="primary-button" type="button" disabled={cleanup.isPending} onClick={() => cleanup.mutate()}>
                {cleanup.isPending ? '正在清理…' : '确认清理'}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  )
}
