import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { apiRequest } from '../api/client'
import {
  isVersionConflict,
  purgeTrashObject,
  restoreTrashObject,
  type FileItem,
  type TrashFolderItem,
  type TrashResponse,
} from '../api/files'
import { purgeKnowledgeBase, restoreKnowledgeBase, type KnowledgeBaseListResponse } from '../api/knowledgeBases'

export default function TrashPage() {
  const queryClient = useQueryClient()
  const [versionConflict, setVersionConflict] = useState<string | null>(null)
  const trashQuery = useQuery({ queryKey: ['trash'], queryFn: () => apiRequest<TrashResponse>('/api/v1/trash') })
  const knowledgeTrashQuery = useQuery({ queryKey: ['trash-knowledge-bases'], queryFn: () => apiRequest<KnowledgeBaseListResponse>('/api/v1/trash/knowledge-bases') })
  const onConflict = (error: unknown) => { if (isVersionConflict(error)) setVersionConflict('数据已被其他操作修改，请重新加载后再试。') }
  const restoreMutation = useMutation({ mutationFn: (file: FileItem) => restoreTrashObject<FileItem>('file', file.file_id, file.row_version), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash'] }); void queryClient.invalidateQueries({ queryKey: ['files'] }) }, onError: onConflict })
  const purgeMutation = useMutation({ mutationFn: (file: FileItem) => purgeTrashObject('file', file.file_id, file.row_version), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash'] }) }, onError: onConflict })
  const restoreFolderMutation = useMutation({ mutationFn: (folder: TrashFolderItem) => restoreTrashObject('folder', folder.folder_id, folder.row_version), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash'] }); void queryClient.invalidateQueries({ queryKey: ['folders'] }); void queryClient.invalidateQueries({ queryKey: ['files'] }) }, onError: onConflict })
  const purgeFolderMutation = useMutation({ mutationFn: (folder: TrashFolderItem) => purgeTrashObject('folder', folder.folder_id, folder.row_version), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash'] }) }, onError: onConflict })
  const restoreKnowledgeMutation = useMutation({ mutationFn: restoreKnowledgeBase, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash-knowledge-bases'] }); void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] }) }, onError: onConflict })
  const purgeKnowledgeMutation = useMutation({ mutationFn: purgeKnowledgeBase, onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['trash-knowledge-bases'] }) }, onError: onConflict })
  const files = trashQuery.data?.files ?? []
  const folders = trashQuery.data?.folders ?? []
  const knowledgeBases = knowledgeTrashQuery.data?.items ?? []
  if (trashQuery.isLoading || knowledgeTrashQuery.isLoading) return <section className="detail-page"><h1>正在加载回收站…</h1></section>
  if (trashQuery.isError || knowledgeTrashQuery.isError) return <section className="detail-page"><Link className="back-link" to="/files"><ArrowLeft size={16} aria-hidden="true" />返回文件</Link><h1>回收站加载失败</h1><p>请稍后重试。</p><button type="button" className="quiet-button" onClick={() => { void trashQuery.refetch(); void knowledgeTrashQuery.refetch() }}>重试</button></section>
  return <section className="detail-page"><Link className="back-link" to="/files"><ArrowLeft size={16} aria-hidden="true" />返回文件</Link><div className="page-heading"><div><span className="eyebrow">本地回收站</span><h1>回收站</h1><p>业务对象默认保留 30 天，永久删除无法撤销。</p></div></div>{versionConflict && <div className="inline-error" role="alert"><span>{versionConflict}</span><button type="button" className="quiet-button" onClick={() => { setVersionConflict(null); void trashQuery.refetch(); void knowledgeTrashQuery.refetch() }}>重新加载</button></div>}<div className="trash-list">{knowledgeBases.map((item) => <div className="trash-row" key={item.knowledge_base_id}><div><strong>{item.name}</strong><span>知识库 · 原始文件仍保留</span></div><div className="heading-actions"><button type="button" className="quiet-button" onClick={() => restoreKnowledgeMutation.mutate(item)}><RotateCcw size={15} aria-hidden="true" />恢复知识库</button><button type="button" className="danger-button" onClick={() => { if (window.confirm(`永久删除知识库“${item.name}”？原始文件会保留，但此操作无法撤销。`)) purgeKnowledgeMutation.mutate(item) }}><Trash2 size={15} aria-hidden="true" />永久删除</button></div></div>)}{folders.map((folder) => <div className="trash-row" key={folder.folder_id}><div><strong>{folder.name}</strong><span>文件夹及其子项</span></div><div className="heading-actions"><button type="button" className="quiet-button" onClick={() => restoreFolderMutation.mutate(folder)}><RotateCcw size={15} aria-hidden="true" />整体恢复</button><button type="button" className="danger-button" onClick={() => { if (window.confirm(`永久删除文件夹“${folder.name}”及其子项？此操作无法撤销。`)) purgeFolderMutation.mutate(folder) }}><Trash2 size={15} aria-hidden="true" />永久删除</button></div></div>)}{files.map((file) => <div className="trash-row" key={file.file_id}><div><strong>{file.display_name}</strong><span>{file.document_type} · {file.folder_name ?? '未分类'}</span></div><div className="heading-actions"><button type="button" className="quiet-button" onClick={() => restoreMutation.mutate(file)}><RotateCcw size={15} aria-hidden="true" />恢复</button><button type="button" className="danger-button" onClick={() => { if (window.confirm(`永久删除“${file.display_name}”？此操作无法撤销。`)) purgeMutation.mutate(file) }}><Trash2 size={15} aria-hidden="true" />永久删除</button></div></div>)}{files.length === 0 && folders.length === 0 && knowledgeBases.length === 0 && <div className="empty-state"><Trash2 size={24} aria-hidden="true" /><strong>回收站为空</strong><span>移入回收站的文件、文件夹和知识库会显示在这里。</span></div>}</div></section>
}
