import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, FileText, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { apiRequest } from '../api/client'
import { isVersionConflict, type FileItem, type FolderItem, type TagItem } from '../api/files'

type Preview = {
  preview_available: boolean
  text?: string | null
  metadata?: { line_count?: number; character_count?: number } | null
}

const statusLabels: Record<string, string> = {
  PARSED: '已解析',
  QUEUED: '待处理',
  PARSING: '处理中',
  PARSE_FAILED: '解析失败',
  IN_TRASH: '回收站',
  STORAGE_MISSING: '文件缺失',
}

export default function FileDetailPage() {
  const { fileId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [versionConflict, setVersionConflict] = useState<string | null>(null)
  const fileQuery = useQuery({
    queryKey: ['file', fileId],
    queryFn: () => apiRequest<FileItem>(`/api/v1/files/${fileId}`),
    enabled: Boolean(fileId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'QUEUED' || status === 'PARSING' ? 1000 : false
    },
  })
  const previewQuery = useQuery({
    queryKey: ['file-preview', fileId],
    queryFn: () => apiRequest<Preview>(`/api/v1/files/${fileId}/preview`),
    enabled: Boolean(fileId),
    refetchInterval: () => {
      const status = fileQuery.data?.status
      return status === 'QUEUED' || status === 'PARSING' ? 1000 : false
    },
  })
  const foldersQuery = useQuery({ queryKey: ['folders'], queryFn: () => apiRequest<{ items: FolderItem[] }>('/api/v1/folders') })
  const tagsQuery = useQuery({ queryKey: ['tags'], queryFn: () => apiRequest<{ items: TagItem[] }>('/api/v1/tags') })
  const relationsQuery = useQuery({
    queryKey: ['file-knowledge-bases', fileId],
    queryFn: () => apiRequest<{ items: Array<{ knowledge_base_id: string; name: string; index_state: string }> }>(`/api/v1/files/${fileId}/knowledge-bases`),
    enabled: Boolean(fileId),
  })
  const onConflict = (error: unknown) => {
    if (isVersionConflict(error)) setVersionConflict('文件已被其他操作修改，请重新加载后再试。')
  }
  const listState = location.state as { fileListSearch?: string; fileListScroll?: number } | null
  const listTarget = `/files${listState?.fileListSearch ?? ''}`
  const restoreState = listState?.fileListScroll === undefined ? null : { restoreFileListScroll: listState.fileListScroll }
  async function returnToList(event: React.MouseEvent<HTMLAnchorElement>) {
    event.preventDefault()
    await queryClient.refetchQueries({ queryKey: ['files'] })
    navigate(listTarget, { state: restoreState })
  }
  const trashMutation = useMutation({
    mutationFn: () => apiRequest<FileItem>(`/api/v1/files/${fileId}?expected_version=${fileQuery.data?.row_version}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['files'] })
      navigate(listTarget, { state: restoreState })
    },
    onError: onConflict,
  })
  const reprocessMutation = useMutation({
    mutationFn: () => apiRequest<{ task_id: string; file: FileItem }>(`/api/v1/files/${fileId}/reprocess`, { method: 'POST' }),
    onSuccess: (result) => {
      queryClient.setQueryData(['file', fileId], result.file)
      void queryClient.invalidateQueries({ queryKey: ['files'] })
    },
  })
  const patchMutation = useMutation({
    mutationFn: (payload: { display_name?: string; folder_id?: string | null }) => apiRequest<FileItem>(`/api/v1/files/${fileId}`, { method: 'PATCH', body: JSON.stringify({ ...payload, row_version: fileQuery.data?.row_version }) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['file', fileId], updated)
      void queryClient.invalidateQueries({ queryKey: ['files'] })
    },
    onError: onConflict,
  })
  const tagMutation = useMutation({
    mutationFn: ({ tagId, active }: { tagId: string; active: boolean }) => apiRequest(`/api/v1/files/${fileId}/tags/${tagId}`, { method: active ? 'DELETE' : 'PUT' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['file', fileId] })
      void queryClient.invalidateQueries({ queryKey: ['files'] })
    },
  })

  if (fileQuery.isLoading) return <section className="detail-page"><span className="eyebrow">文件详情</span><h1>正在加载…</h1></section>
  if (fileQuery.isError || !fileQuery.data) return <section className="detail-page"><Link className="back-link" to={listTarget} state={restoreState} onClick={returnToList}><ArrowLeft size={16} aria-hidden="true" />返回文件</Link><h1>文件不可用</h1><p>文件可能已被永久删除，或当前本地服务未返回详情。</p></section>

  const file = fileQuery.data
  const activeTagIds = new Set(file.tags.map((tag) => tag.tag_id))
  return (
    <section className="detail-page">
      <Link className="back-link" to={listTarget} state={restoreState} onClick={returnToList}><ArrowLeft size={16} aria-hidden="true" />返回文件</Link>
      {versionConflict && <div className="inline-error" role="alert"><span>{versionConflict}</span><button type="button" className="quiet-button" onClick={() => { setVersionConflict(null); void fileQuery.refetch() }}>重新加载</button></div>}
      <div className="detail-heading">
        <div><span className="eyebrow">{file.document_type}</span><h1>{file.display_name}</h1><p>{file.folder_name ?? '未分类'} · {formatBytes(file.byte_size)} · {statusLabels[file.status] ?? file.status}</p></div>
        <div className="heading-actions">
          <a className="quiet-button" href={`/api/v1/files/${file.file_id}/content`} target="_blank" rel="noreferrer"><FileText size={16} aria-hidden="true" />打开原文</a>
          <button type="button" className="quiet-button" disabled={!file.can_reprocess || reprocessMutation.isPending} onClick={() => reprocessMutation.mutate()}><RotateCcw size={16} aria-hidden="true" />重新处理</button>
          <button type="button" className="danger-button" onClick={() => trashMutation.mutate()}><Trash2 size={16} aria-hidden="true" />移入回收站</button>
        </div>
      </div>
      <div className="detail-grid">
        <section className="detail-section">
          <h2>解析文本</h2>
          {previewQuery.isLoading ? <div className="detail-empty">正在加载解析文本…</div> : previewQuery.isError ? <div className="detail-empty">解析文本加载失败。</div> : previewQuery.data?.preview_available ? <pre className="text-preview">{previewQuery.data.text}</pre> : <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>当前文件还没有可用的解析文本。</span></div>}
        </section>
        <section className="detail-section">
          <h2>文件设置</h2>
          <form className="detail-form" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); const name = String(form.get('display_name') ?? '').trim(); if (name && name !== file.display_name) patchMutation.mutate({ display_name: name }) }}><label>显示名称<input name="display_name" defaultValue={file.display_name} maxLength={255} /></label><button type="submit" className="quiet-button">保存名称</button></form>
          <label className="detail-field">文件夹<select value={file.folder_id ?? ''} onChange={(event) => patchMutation.mutate({ folder_id: event.target.value || null })}><option value="">未分类</option>{foldersQuery.data?.items.map((folder) => <option key={folder.folder_id} value={folder.folder_id}>{folder.name}</option>)}</select></label>
          <div className="detail-tags">{tagsQuery.data?.items.map((tag) => <button type="button" className={`tag-chip ${activeTagIds.has(tag.tag_id) ? 'tag-chip--active' : ''}`} key={tag.tag_id} onClick={() => tagMutation.mutate({ tagId: tag.tag_id, active: activeTagIds.has(tag.tag_id) })}>{tag.name}</button>)}</div>
          <h2>元数据</h2>
          <dl className="metadata-list"><div><dt>原始文件名</dt><dd>{file.display_name}</dd></div><div><dt>内容哈希</dt><dd>{file.content_hash}</dd></div><div><dt>最近更新</dt><dd>{new Date(file.updated_at).toLocaleString('zh-CN')}</dd></div><div><dt>解析状态</dt><dd>{statusLabels[file.status] ?? file.status}</dd></div>{file.parse_failure_stage && <div><dt>失败阶段</dt><dd>{file.parse_failure_stage}</dd></div>}{file.parse_error_id && <div><dt>错误 ID</dt><dd>{file.parse_error_id}</dd></div>}<div><dt>重试次数</dt><dd>{file.parse_retry_count}</dd></div><div><dt>所在知识库</dt><dd>{relationsQuery.data?.items.map((item) => `${item.name}（${item.index_state}）`).join('、') || '暂无'}</dd></div></dl>
        </section>
      </div>
    </section>
  )
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
