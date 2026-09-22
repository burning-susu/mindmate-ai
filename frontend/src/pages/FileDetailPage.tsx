import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, FileText, RotateCcw, Trash2 } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { apiRequest } from '../api/client'
import type { FileItem } from './FilesPage'

type Preview = { preview_available: boolean; text?: string | null; metadata?: { line_count?: number; character_count?: number } | null }

const statusLabels: Record<string, string> = { PARSED: '已解析', QUEUED: '待处理', PARSING: '处理中', IN_TRASH: '回收站', STORAGE_MISSING: '文件缺失' }

export default function FileDetailPage() {
  const { fileId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileQuery = useQuery({ queryKey: ['file', fileId], queryFn: () => apiRequest<FileItem>(`/api/v1/files/${fileId}`), enabled: Boolean(fileId) })
  const previewQuery = useQuery({ queryKey: ['file-preview', fileId], queryFn: () => apiRequest<Preview>(`/api/v1/files/${fileId}/preview`), enabled: Boolean(fileId) })
  const trashMutation = useMutation({ mutationFn: () => apiRequest(`/api/v1/files/${fileId}?expected_version=${fileQuery.data?.row_version}`, { method: 'DELETE' }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['files'] }); navigate('/files') } })
  const reprocessMutation = useMutation({ mutationFn: () => apiRequest(`/api/v1/files/${fileId}/reprocess`, { method: 'POST' }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['file', fileId] }) } })

  if (fileQuery.isLoading) return <section className="detail-page"><span className="eyebrow">文件详情</span><h1>正在加载…</h1></section>
  if (fileQuery.isError || !fileQuery.data) return <section className="detail-page"><Link className="back-link" to="/files"><ArrowLeft size={16} aria-hidden="true" />返回文件</Link><h1>文件不可用</h1><p>文件可能已被永久删除，或当前本地服务未返回详情。</p></section>
  const file = fileQuery.data
  return <section className="detail-page"><Link className="back-link" to="/files"><ArrowLeft size={16} aria-hidden="true" />返回文件</Link><div className="detail-heading"><div><span className="eyebrow">{file.document_type}</span><h1>{file.display_name}</h1><p>{file.folder_name ?? '未分类'} · {formatBytes(file.byte_size)} · {statusLabels[file.status] ?? file.status}</p></div><div className="heading-actions"><button type="button" className="quiet-button" onClick={() => reprocessMutation.mutate()}><RotateCcw size={16} aria-hidden="true" />重新处理</button><button type="button" className="danger-button" onClick={() => trashMutation.mutate()}><Trash2 size={16} aria-hidden="true" />移入回收站</button></div></div><div className="detail-grid"><section className="detail-section"><h2>解析文本</h2>{previewQuery.data?.preview_available ? <pre className="text-preview">{previewQuery.data.text}</pre> : <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>当前文件还没有可用的解析文本。</span></div>}</section><section className="detail-section"><h2>元数据</h2><dl className="metadata-list"><div><dt>原始文件名</dt><dd>{file.display_name}</dd></div><div><dt>内容哈希</dt><dd>{file.content_hash}</dd></div><div><dt>最近更新</dt><dd>{new Date(file.updated_at).toLocaleString('zh-CN')}</dd></div><div><dt>解析状态</dt><dd>{statusLabels[file.status] ?? file.status}</dd></div></dl>{file.tags.length > 0 && <div className="detail-tags">{file.tags.map((tag) => <span className="tag-chip" key={tag.tag_id}>{tag.name}</span>)}</div>}</section></div></section>
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
