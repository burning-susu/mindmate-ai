import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileUp, Folder, FolderPlus, MoreHorizontal, Plus, Search, Tag as TagIcon, Trash2, X } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { apiRequest, apiUpload } from '../api/client'

type Tag = { tag_id: string; name: string; color?: string | null }
type FolderItem = { folder_id: string; parent_folder_id?: string | null; name: string; file_count: number }
export type FileItem = {
  file_id: string
  display_name: string
  document_type: string
  extension: string
  folder_id?: string | null
  folder_name?: string | null
  status: string
  content_hash: string
  byte_size: number
  updated_at: string
  row_version: number
  tags: Tag[]
  has_parsed_text: boolean
  parsed_metadata?: { line_count?: number; character_count?: number } | null
}
type FileListResponse = { items: FileItem[]; next_cursor?: string | null }
type ImportItem = {
  item_index: number
  original_name: string
  status: string
  duplicate_status: string
  file_id?: string | null
  error?: string | null
  error_code?: string
}
type ImportResponse = { import_id: string; status: string; items: ImportItem[] }

const statusLabels: Record<string, string> = {
  PARSED: '已解析',
  QUEUED: '待处理',
  PARSING: '处理中',
  IN_TRASH: '回收站',
  STORAGE_MISSING: '文件缺失',
  READY: '可用',
  PARSE_FAILED: '解析失败',
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function FileStatus({ status }: { status: string }) {
  return <span className={`file-status file-status--${status.toLowerCase()}`}>{statusLabels[status] ?? status}</span>
}

export default function FilesPage() {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [folderId, setFolderId] = useState<string | undefined>()
  const [selected, setSelected] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)
  const [importResult, setImportResult] = useState<ImportResponse | null>(null)
  const [newFolderName, setNewFolderName] = useState('')

  const filesQuery = useQuery({
    queryKey: ['files', query, folderId],
    queryFn: () => apiRequest<FileListResponse>(`/api/v1/files?limit=100${query ? `&q=${encodeURIComponent(query)}` : ''}${folderId ? `&folder_id=${folderId}` : ''}`),
  })
  const foldersQuery = useQuery({ queryKey: ['folders'], queryFn: () => apiRequest<{ items: FolderItem[] }>('/api/v1/folders') })
  const tagsQuery = useQuery({ queryKey: ['tags'], queryFn: () => apiRequest<{ items: Tag[] }>('/api/v1/tags') })

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => apiUpload<ImportResponse>('/api/v1/file-imports', files, { folder_id: folderId }),
    onSuccess: (result) => {
      setImportResult(result)
      void queryClient.invalidateQueries({ queryKey: ['files'] })
      void queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (file: FileItem) => apiRequest(`/api/v1/files/${file.file_id}?expected_version=${file.row_version}`, { method: 'DELETE' }),
    onSuccess: () => {
      setSelected([])
      void queryClient.invalidateQueries({ queryKey: ['files'] })
    },
  })
  const folderMutation = useMutation({
    mutationFn: (name: string) => apiRequest('/api/v1/folders', { method: 'POST', body: JSON.stringify({ name, parent_folder_id: folderId }) }),
    onSuccess: () => {
      setNewFolderName('')
      void queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
  })
  const duplicateMutation = useMutation({
    mutationFn: ({ importId, itemIndex, decision }: { importId: string; itemIndex: number; decision: string }) =>
      apiRequest<ImportResponse>(`/api/v1/file-imports/${importId}/duplicate-decisions`, {
        method: 'POST',
        body: JSON.stringify({ decisions: [{ item_index: itemIndex, decision }] }),
      }),
    onSuccess: (result) => {
      setImportResult(result)
      void queryClient.invalidateQueries({ queryKey: ['files'] })
    },
  })

  const folders = foldersQuery.data?.items ?? []
  const files = filesQuery.data?.items ?? []
  const tags = tagsQuery.data?.items ?? []
  const pendingDuplicates = useMemo(() => importResult?.items.filter((item) => item.duplicate_status === 'PENDING_DECISION') ?? [], [importResult])
  const selectedFiles = files.filter((file) => selected.includes(file.file_id))

  function chooseFiles(fileList: FileList | File[]) {
    const incoming = Array.from(fileList)
    if (incoming.length) uploadMutation.mutate(incoming)
  }

  function toggleSelected(fileId: string) {
    setSelected((current) => current.includes(fileId) ? current.filter((id) => id !== fileId) : [...current, fileId])
  }

  function selectAll() {
    setSelected(selected.length === files.length ? [] : files.map((file) => file.file_id))
  }

  return (
    <section className="files-page" aria-labelledby="files-heading">
      <div className="page-heading">
        <div>
          <span className="eyebrow">资料管理</span>
          <h1 id="files-heading">文件</h1>
          <p>在本地整理资料，文件副本不会依赖原始来源路径。</p>
        </div>
        <div className="heading-actions">
          <Link className="quiet-button" to="/trash"><Trash2 size={16} aria-hidden="true" />回收站</Link>
          <button className="primary-button" type="button" onClick={() => inputRef.current?.click()}><FileUp size={16} aria-hidden="true" />导入文件</button>
          <input ref={inputRef} className="visually-hidden" type="file" multiple accept=".pdf,.docx,.pptx,.txt,.md,.markdown" onChange={(event) => { if (event.target.files) chooseFiles(event.target.files); event.currentTarget.value = '' }} />
        </div>
      </div>

      <div className="files-layout">
        <aside className="folder-panel" aria-label="文件夹">
          <div className="panel-heading"><span>目录</span><FolderPlus size={16} aria-hidden="true" /></div>
          <button className={`folder-row ${!folderId ? 'folder-row--active' : ''}`} type="button" onClick={() => setFolderId(undefined)}><Folder size={16} aria-hidden="true" /><span>全部文件</span><small>{files.length}</small></button>
          {folders.filter((folder) => !folder.parent_folder_id).map((folder) => <button key={folder.folder_id} className={`folder-row ${folderId === folder.folder_id ? 'folder-row--active' : ''}`} type="button" onClick={() => setFolderId(folder.folder_id)}><Folder size={16} aria-hidden="true" /><span>{folder.name}</span><small>{folder.file_count}</small></button>)}
          <form className="new-folder-form" onSubmit={(event) => { event.preventDefault(); if (newFolderName.trim()) folderMutation.mutate(newFolderName.trim()) }}>
            <input value={newFolderName} onChange={(event) => setNewFolderName(event.target.value)} aria-label="新文件夹名称" placeholder="新建文件夹" maxLength={100} />
            <button type="submit" aria-label="创建文件夹" title="创建文件夹"><Plus size={15} aria-hidden="true" /></button>
          </form>
        </aside>

        <div className="files-main">
          <div className="files-toolbar">
            <label className="search-field"><Search size={16} aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名" aria-label="搜索文件名" /></label>
            <select value={folderId ?? ''} onChange={(event) => setFolderId(event.target.value || undefined)} aria-label="按文件夹筛选"><option value="">所有文件夹</option>{folders.map((folder) => <option value={folder.folder_id} key={folder.folder_id}>{folder.name}</option>)}</select>
            <span className="toolbar-meta">{files.length} 个文件 · 支持 PDF、DOCX、PPTX、TXT、Markdown</span>
          </div>

          <div className={`drop-zone ${dragging ? 'drop-zone--active' : ''}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true) }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFiles(event.dataTransfer.files) }}>
            <FileUp size={19} aria-hidden="true" /><span>拖放文件到这里，或 <button type="button" onClick={() => inputRef.current?.click()}>选择文件</button></span><small>单文件 50 MB · 单批 20 个 · 总量 500 MB</small>
          </div>

          {importResult && <div className="import-summary" role="status"><div><strong>导入任务 {importResult.status === 'BLOCKED' ? '等待重复决策' : '已处理'}</strong><span>{importResult.items.filter((item) => item.status === 'IMPORTED' || item.status === 'REUSED').length} 个成功，{importResult.items.filter((item) => item.error).length} 个未导入</span></div><button type="button" className="icon-button" onClick={() => setImportResult(null)} aria-label="关闭导入结果"><X size={16} aria-hidden="true" /></button>{pendingDuplicates.map((item) => <div className="duplicate-row" key={item.item_index}><span>{item.original_name}</span><button type="button" onClick={() => duplicateMutation.mutate({ importId: importResult.import_id, itemIndex: item.item_index, decision: 'REUSE_EXISTING' })}>复用现有</button><button type="button" onClick={() => duplicateMutation.mutate({ importId: importResult.import_id, itemIndex: item.item_index, decision: 'CREATE_SEPARATE_RECORD' })}>另存记录</button><button type="button" onClick={() => duplicateMutation.mutate({ importId: importResult.import_id, itemIndex: item.item_index, decision: 'SKIP' })}>跳过</button></div>)}</div>}

          {selectedFiles.length > 0 && <div className="selection-bar"><strong>已选 {selectedFiles.length} 个</strong><button type="button" onClick={() => selectedFiles.forEach((file) => deleteMutation.mutate(file))}><Trash2 size={15} aria-hidden="true" />移入回收站</button><button type="button" onClick={() => setSelected([])}>取消选择</button></div>}

          <div className="file-table-wrap">
            <table className="file-table"><thead><tr><th><input type="checkbox" checked={files.length > 0 && selected.length === files.length} onChange={selectAll} aria-label="选择全部文件" /></th><th>名称</th><th>类型</th><th>状态</th><th>标签</th><th>大小</th><th>更新</th><th aria-label="操作" /></tr></thead><tbody>{files.map((file) => <tr key={file.file_id}><td><input type="checkbox" checked={selected.includes(file.file_id)} onChange={() => toggleSelected(file.file_id)} aria-label={`选择 ${file.display_name}`} /></td><td><Link className="file-name" to={`/files/${file.file_id}`}><FileTextGlyph type={file.document_type} /><span>{file.display_name}</span></Link></td><td>{file.document_type}</td><td><FileStatus status={file.status} /></td><td><span className="tag-list">{file.tags.map((tag) => <span className="tag-chip" key={tag.tag_id} style={tag.color ? { borderColor: tag.color, color: tag.color } : undefined}><TagIcon size={12} aria-hidden="true" />{tag.name}</span>)}</span></td><td>{formatBytes(file.byte_size)}</td><td>{formatDate(file.updated_at)}</td><td><button className="icon-button icon-button--small" type="button" onClick={() => deleteMutation.mutate(file)} aria-label={`移入回收站 ${file.display_name}`} title="移入回收站"><MoreHorizontal size={16} aria-hidden="true" /></button></td></tr>)}</tbody></table>
            {files.length === 0 && <div className="empty-state"><FileUp size={24} aria-hidden="true" /><strong>{query ? '没有匹配的文件' : '还没有文件'}</strong><span>{query ? '尝试清除搜索条件。' : '导入 PDF、DOCX、PPTX、TXT 或 Markdown 开始整理。'}</span><button type="button" className="primary-button" onClick={() => inputRef.current?.click()}>导入文件</button></div>}
          </div>
          {uploadMutation.isPending && <div className="inline-progress">正在校验并复制文件…</div>}
          {uploadMutation.isError && <div className="inline-error">{uploadMutation.error instanceof Error ? uploadMutation.error.message : '导入失败，请稍后重试。'}</div>}
          {tags.length > 0 && <div className="tag-hint"><TagIcon size={15} aria-hidden="true" />已创建 {tags.length} 个标签，可在文件详情中编辑。</div>}
        </div>
      </div>
    </section>
  )
}

function FileTextGlyph({ type }: { type: string }) {
  return <span className={`file-type-glyph file-type-glyph--${type.toLowerCase()}`} aria-hidden="true">{type === 'MARKDOWN' ? 'M' : type.slice(0, 1)}</span>
}
