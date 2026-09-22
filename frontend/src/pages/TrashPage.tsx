import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, RotateCcw, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { apiRequest } from '../api/client'
import type { FileItem } from './FilesPage'

type TrashResponse = { files: FileItem[]; folders: Array<{ folder_id: string; name: string }> }

export default function TrashPage() {
  const queryClient = useQueryClient()
  const trashQuery = useQuery({ queryKey: ['trash'], queryFn: () => apiRequest<TrashResponse>('/api/v1/trash') })
  const restoreMutation = useMutation({ mutationFn: (fileId: string) => apiRequest(`/api/v1/trash/file/${fileId}/restore`, { method: 'POST' }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash'] }); void queryClient.invalidateQueries({ queryKey: ['files'] }) } })
  const purgeMutation = useMutation({ mutationFn: (fileId: string) => apiRequest(`/api/v1/trash/file/${fileId}?confirmed=true`, { method: 'DELETE' }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash'] }) } })
  const restoreFolderMutation = useMutation({ mutationFn: (folderId: string) => apiRequest(`/api/v1/trash/folder/${folderId}/restore`, { method: 'POST' }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash'] }); void queryClient.invalidateQueries({ queryKey: ['folders'] }); void queryClient.invalidateQueries({ queryKey: ['files'] }) } })
  const purgeFolderMutation = useMutation({ mutationFn: (folderId: string) => apiRequest(`/api/v1/trash/folder/${folderId}?confirmed=true`, { method: 'DELETE' }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash'] }) } })
  const files = trashQuery.data?.files ?? []
  const folders = trashQuery.data?.folders ?? []
  if (trashQuery.isLoading) return <section className="detail-page"><h1>正在加载回收站…</h1></section>
  if (trashQuery.isError) return <section className="detail-page"><Link className="back-link" to="/files"><ArrowLeft size={16} aria-hidden="true" />返回文件</Link><h1>回收站加载失败</h1><p>{trashQuery.error instanceof Error ? trashQuery.error.message : '请稍后重试。'}</p><button type="button" className="quiet-button" onClick={() => void trashQuery.refetch()}>重试</button></section>
  return <section className="detail-page"><Link className="back-link" to="/files"><ArrowLeft size={16} aria-hidden="true" />返回文件</Link><div className="page-heading"><div><span className="eyebrow">本地回收站</span><h1>回收站</h1><p>文件默认保留 30 天，恢复后回到原文件夹。</p></div></div><div className="trash-list">{folders.map((folder) => <div className="trash-row" key={folder.folder_id}><div><strong>{folder.name}</strong><span>文件夹及其子项</span></div><div className="heading-actions"><button type="button" className="quiet-button" onClick={() => restoreFolderMutation.mutate(folder.folder_id)}><RotateCcw size={15} aria-hidden="true" />整体恢复</button><button type="button" className="danger-button" onClick={() => { if (window.confirm(`永久删除文件夹“${folder.name}”及其子项？此操作无法撤销。`)) purgeFolderMutation.mutate(folder.folder_id) }}><Trash2 size={15} aria-hidden="true" />永久删除</button></div></div>)}{files.map((file) => <div className="trash-row" key={file.file_id}><div><strong>{file.display_name}</strong><span>{file.document_type} · {file.folder_name ?? '未分类'}</span></div><div className="heading-actions"><button type="button" className="quiet-button" onClick={() => restoreMutation.mutate(file.file_id)}><RotateCcw size={15} aria-hidden="true" />恢复</button><button type="button" className="danger-button" onClick={() => { if (window.confirm(`永久删除“${file.display_name}”？此操作无法撤销。`)) purgeMutation.mutate(file.file_id) }}><Trash2 size={15} aria-hidden="true" />永久删除</button></div></div>)}{files.length === 0 && folders.length === 0 && <div className="empty-state"><Trash2 size={24} aria-hidden="true" /><strong>回收站为空</strong><span>移入回收站的文件和文件夹会显示在这里。</span></div>}</div></section>
}
