import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileUp, Folder, FolderMinus, FolderPlus, MoreHorizontal, Plus, Search, Tag as TagIcon, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { apiRequest, apiUpload } from '../api/client'
import {
  deleteFolder as deleteFolderRequest,
  isVersionConflict,
  type FileItem,
  type FileListResponse,
  type FolderItem,
  type TagItem,
} from '../api/files'

export type { FileItem } from '../api/files'
type ImportItem = {
  item_index: number
  original_name: string
  status: string
  duplicate_status: string
  file_id?: string | null
  error?: string | null
  error_code?: string
  parse_status?: string | null
}
type ImportResponse = { import_id: string; status: string; phase?: string | null; progress?: number | null; items: ImportItem[] }

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

function FolderTree({ folders, parentId, selectedId, onSelect, onDelete, depth = 0 }: { folders: FolderItem[]; parentId?: string; selectedId?: string; onSelect: (id: string) => void; onDelete: (folder: FolderItem, strategy: 'MOVE_CHILDREN' | 'TRASH_RECURSIVE') => void; depth?: number }) {
  return folders.filter((folder) => (folder.parent_folder_id ?? undefined) === parentId).map((folder) => (
    <div key={folder.folder_id}>
      <div className="folder-tree-row" style={{ paddingLeft: depth * 14 }}>
        <button className={`folder-row ${selectedId === folder.folder_id ? 'folder-row--active' : ''}`} type="button" onClick={() => onSelect(folder.folder_id)}><Folder size={16} aria-hidden="true" /><span>{folder.name}</span><small>{folder.file_count}</small></button>
        <button className="folder-action" type="button" title="仅删除目录并保留内容" aria-label={`仅删除目录 ${folder.name}`} onClick={() => onDelete(folder, 'MOVE_CHILDREN')}><FolderMinus size={14} aria-hidden="true" /></button>
        <button className="folder-action" type="button" title="目录和内容移入回收站" aria-label={`目录和内容移入回收站 ${folder.name}`} onClick={() => onDelete(folder, 'TRASH_RECURSIVE')}><Trash2 size={14} aria-hidden="true" /></button>
      </div>
      <FolderTree folders={folders} parentId={folder.folder_id} selectedId={selectedId} onSelect={onSelect} onDelete={onDelete} depth={depth + 1} />
    </div>
  ))
}

export default function FilesPage() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const inputRef = useRef<HTMLInputElement>(null)
  const query = searchParams.get('q') ?? ''
  const folderId = searchParams.get('folder_id') ?? undefined
  const tagId = searchParams.get('tag_id') ?? undefined
  const documentType = searchParams.get('document_type') ?? undefined
  const status = searchParams.get('status') ?? undefined
  const sort = searchParams.get('sort') ?? 'updated_at'
  const [batchFolderId, setBatchFolderId] = useState('')
  const [batchTagId, setBatchTagId] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)
  const [importResult, setImportResult] = useState<ImportResponse | null>(null)
  const [newFolderName, setNewFolderName] = useState('')
  const [newTagName, setNewTagName] = useState('')
  const [versionConflict, setVersionConflict] = useState<string | null>(null)

  const filesQuery = useQuery({
    queryKey: ['files', query, folderId, tagId, documentType, status, sort],
    queryFn: () => {
      const params = new URLSearchParams({ limit: '100', sort })
      if (query) params.set('q', query)
      if (folderId) params.set('folder_id', folderId)
      if (tagId) params.set('tag_id', tagId)
      if (documentType) params.set('document_type', documentType)
      if (status) params.set('status', status)
      return apiRequest<FileListResponse>(`/api/v1/files?${params}`)
    },
    refetchInterval: (query) => {
      const data = query.state.data as FileListResponse | undefined
      return data?.items.some((file) => file.status === 'QUEUED' || file.status === 'PARSING') ? 1000 : false
    },
  })
  const importTaskQuery = useQuery({
    queryKey: ['file-import', importResult?.import_id],
    queryFn: () => apiRequest<ImportResponse>(`/api/v1/file-imports/${importResult?.import_id}`),
    enabled: Boolean(importResult?.import_id),
    refetchInterval: (query) => {
      const status = (query.state.data as ImportResponse | undefined)?.status
      return status === 'QUEUED' || status === 'RUNNING' || status === 'PARSING' ? 1000 : false
    },
  })
  const foldersQuery = useQuery({ queryKey: ['folders'], queryFn: () => apiRequest<{ items: FolderItem[] }>('/api/v1/folders') })
  const tagsQuery = useQuery({ queryKey: ['tags'], queryFn: () => apiRequest<{ items: TagItem[] }>('/api/v1/tags') })

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
    onError: (error) => {
      if (isVersionConflict(error)) setVersionConflict('文件已被其他操作修改，请重新加载后再试。')
    },
  })
  const folderMutation = useMutation({
    mutationFn: (name: string) => apiRequest('/api/v1/folders', { method: 'POST', body: JSON.stringify({ name, parent_folder_id: folderId }) }),
    onSuccess: () => {
      setNewFolderName('')
      void queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
  })
  const deleteFolderMutation = useMutation({
    mutationFn: ({ folder, strategy }: { folder: FolderItem; strategy: 'MOVE_CHILDREN' | 'TRASH_RECURSIVE' }) => deleteFolderRequest(folder, strategy),
    onSuccess: () => {
      updateFilter('folder_id')
      void queryClient.invalidateQueries({ queryKey: ['folders'] })
      void queryClient.invalidateQueries({ queryKey: ['files'] })
    },
    onError: (error) => {
      if (isVersionConflict(error)) setVersionConflict('文件夹已被其他操作修改，请重新加载后再试。')
    },
  })
  const tagMutation = useMutation({
    mutationFn: (name: string) => apiRequest('/api/v1/tags', { method: 'POST', body: JSON.stringify({ name }) }),
    onSuccess: () => {
      setNewTagName('')
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
    },
  })
  const batchMutation = useMutation({
    mutationFn: ({ action, folderId: targetFolderId, targetTagId }: { action: string; folderId?: string | null; targetTagId?: string }) => apiRequest('/api/v1/files/batch', {
      method: 'POST',
      body: JSON.stringify({ file_ids: selected, action, ...(folderId !== undefined ? { folder_id: targetFolderId } : {}), ...(targetTagId ? { tag_id: targetTagId } : {}) }),
    }),
    onSuccess: () => {
      setSelected([])
      void queryClient.invalidateQueries({ queryKey: ['files'] })
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
  const activeImportResult = importTaskQuery.data ?? importResult
  const pendingDuplicates = useMemo(() => activeImportResult?.items.filter((item) => item.duplicate_status === 'PENDING_DECISION') ?? [], [activeImportResult])
  const selectedFiles = files.filter((file) => selected.includes(file.file_id))

  useEffect(() => {
    const routeState = location.state as { restoreFileListScroll?: number } | null
    if (!filesQuery.isSuccess || routeState?.restoreFileListScroll === undefined) return
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: routeState.restoreFileListScroll, behavior: 'auto' })
      navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [filesQuery.isSuccess, location.pathname, location.search, location.state, navigate])

  function updateFilter(name: string, value?: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(name, value)
      else next.delete(name)
      return next
    }, { replace: true })
  }

  function openFile(event: React.MouseEvent<HTMLAnchorElement>, fileId: string) {
    event.preventDefault()
    navigate(`/files/${fileId}`, {
      state: { fileListSearch: location.search, fileListScroll: window.scrollY },
    })
  }

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

  function deleteFolder(folder: FolderItem, strategy: 'MOVE_CHILDREN' | 'TRASH_RECURSIVE') {
    const message = strategy === 'TRASH_RECURSIVE' ? `将“${folder.name}”及其内容移入回收站？` : `仅删除“${folder.name}”，保留并上移其内容？`
    if (window.confirm(message)) deleteFolderMutation.mutate({ folder, strategy })
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
          <button className={`folder-row ${!folderId ? 'folder-row--active' : ''}`} type="button" onClick={() => updateFilter('folder_id')}><Folder size={16} aria-hidden="true" /><span>全部文件</span><small>{files.length}</small></button>
          <FolderTree folders={folders} selectedId={folderId} onSelect={(id) => updateFilter('folder_id', id)} onDelete={deleteFolder} />
          <form className="new-folder-form" onSubmit={(event) => { event.preventDefault(); if (newFolderName.trim()) folderMutation.mutate(newFolderName.trim()) }}>
            <input value={newFolderName} onChange={(event) => setNewFolderName(event.target.value)} aria-label="新文件夹名称" placeholder="新建文件夹" maxLength={100} />
            <button type="submit" aria-label="创建文件夹" title="创建文件夹"><Plus size={15} aria-hidden="true" /></button>
          </form>
          <form className="new-folder-form" onSubmit={(event) => { event.preventDefault(); if (newTagName.trim()) tagMutation.mutate(newTagName.trim()) }}>
            <input value={newTagName} onChange={(event) => setNewTagName(event.target.value)} aria-label="新标签名称" placeholder="新建标签" maxLength={30} />
            <button type="submit" aria-label="创建标签" title="创建标签"><TagIcon size={15} aria-hidden="true" /></button>
          </form>
        </aside>

        <div className="files-main">
          <div className="files-toolbar">
            <label className="search-field"><Search size={16} aria-hidden="true" /><input value={query} onChange={(event) => updateFilter('q', event.target.value)} placeholder="搜索名称、标签或正文" aria-label="搜索文件" /></label>
            <select value={folderId ?? ''} onChange={(event) => updateFilter('folder_id', event.target.value)} aria-label="按文件夹筛选"><option value="">所有文件夹</option>{folders.map((folder) => <option value={folder.folder_id} key={folder.folder_id}>{folder.name}</option>)}</select>
            <select value={tagId ?? ''} onChange={(event) => updateFilter('tag_id', event.target.value)} aria-label="按标签筛选"><option value="">所有标签</option>{tags.map((tag) => <option value={tag.tag_id} key={tag.tag_id}>{tag.name}</option>)}</select>
            <select value={documentType ?? ''} onChange={(event) => updateFilter('document_type', event.target.value)} aria-label="按类型筛选"><option value="">所有类型</option>{['PDF', 'DOCX', 'PPTX', 'TXT', 'MARKDOWN'].map((type) => <option value={type} key={type}>{type}</option>)}</select>
            <select value={status ?? ''} onChange={(event) => updateFilter('status', event.target.value)} aria-label="按状态筛选"><option value="">所有状态</option>{Object.entries(statusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select>
            <select value={sort} onChange={(event) => updateFilter('sort', event.target.value === 'updated_at' ? undefined : event.target.value)} aria-label="排序"><option value="updated_at">最近更新</option><option value="created_at">最近导入</option><option value="name">文件名</option><option value="size">大小</option><option value="type">类型</option></select>
            <span className="toolbar-meta">{files.length} 个文件 · 支持 PDF、DOCX、PPTX、TXT、Markdown</span>
          </div>

          <div className={`drop-zone ${dragging ? 'drop-zone--active' : ''}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true) }} onDragOver={(event) => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFiles(event.dataTransfer.files) }}>
            <FileUp size={19} aria-hidden="true" /><span>拖放文件到这里，或 <button type="button" onClick={() => inputRef.current?.click()}>选择文件</button></span><small>单文件 50 MB · 单批 20 个 · 总量 500 MB</small>
          </div>

          {activeImportResult && <div className="import-summary" role="status"><div><strong>导入任务 {activeImportResult.status === 'BLOCKED' ? '等待重复决策' : activeImportResult.status === 'QUEUED' || activeImportResult.status === 'RUNNING' || activeImportResult.status === 'PARSING' ? '解析处理中' : activeImportResult.status === 'FAILED' ? '解析失败' : '已完成'}</strong><span>{activeImportResult.items.filter((item) => item.status === 'IMPORTED' || item.status === 'REUSED').length} 个已加入，{activeImportResult.items.filter((item) => item.error || item.parse_status === 'PARSE_FAILED').length} 个未完成</span></div><button type="button" className="icon-button" onClick={() => setImportResult(null)} aria-label="关闭导入结果"><X size={16} aria-hidden="true" /></button>{pendingDuplicates.map((item) => <div className="duplicate-row" key={item.item_index}><span>{item.original_name}</span><button type="button" onClick={() => duplicateMutation.mutate({ importId: activeImportResult.import_id, itemIndex: item.item_index, decision: 'REUSE_EXISTING' })}>复用现有</button><button type="button" onClick={() => duplicateMutation.mutate({ importId: activeImportResult.import_id, itemIndex: item.item_index, decision: 'CREATE_SEPARATE_RECORD' })}>另存记录</button><button type="button" onClick={() => duplicateMutation.mutate({ importId: activeImportResult.import_id, itemIndex: item.item_index, decision: 'SKIP' })}>跳过</button></div>)}</div>}

          {selectedFiles.length > 0 && <div className="selection-bar"><strong>已选 {selectedFiles.length} 个</strong><select value={batchFolderId} onChange={(event) => setBatchFolderId(event.target.value)} aria-label="批量目标文件夹"><option value="">未分类</option>{folders.map((folder) => <option key={folder.folder_id} value={folder.folder_id}>{folder.name}</option>)}</select><button type="button" onClick={() => batchMutation.mutate({ action: 'MOVE', folderId: batchFolderId || null })}>移动</button><select value={batchTagId} onChange={(event) => setBatchTagId(event.target.value)} aria-label="批量目标标签"><option value="">选择标签</option>{tags.map((tag) => <option key={tag.tag_id} value={tag.tag_id}>{tag.name}</option>)}</select><button type="button" disabled={!batchTagId} onClick={() => batchMutation.mutate({ action: 'ADD_TAG', targetTagId: batchTagId })}>添加标签</button><button type="button" disabled={!batchTagId} onClick={() => batchMutation.mutate({ action: 'REMOVE_TAG', targetTagId: batchTagId })}>移除标签</button><button type="button" onClick={() => batchMutation.mutate({ action: 'REPROCESS' })}>重新处理</button><button type="button" onClick={() => batchMutation.mutate({ action: 'TRASH' })}><Trash2 size={15} aria-hidden="true" />移入回收站</button><button type="button" onClick={() => setSelected([])}>取消</button></div>}

          <div className="file-table-wrap">
            <table className="file-table"><thead><tr><th><input type="checkbox" checked={files.length > 0 && selected.length === files.length} onChange={selectAll} aria-label="选择全部文件" /></th><th>名称</th><th>类型</th><th>状态</th><th>标签</th><th>大小</th><th>更新</th><th aria-label="操作" /></tr></thead><tbody>{files.map((file) => <tr key={file.file_id}><td><input type="checkbox" checked={selected.includes(file.file_id)} onChange={() => toggleSelected(file.file_id)} aria-label={`选择 ${file.display_name}`} /></td><td><Link className="file-name" to={`/files/${file.file_id}`} onClick={(event) => openFile(event, file.file_id)}><FileTextGlyph type={file.document_type} /><span>{file.display_name}</span></Link></td><td>{file.document_type}</td><td><FileStatus status={file.status} /></td><td><span className="tag-list">{file.tags.map((tag) => <span className="tag-chip" key={tag.tag_id} style={tag.color ? { borderColor: tag.color, color: tag.color } : undefined}><TagIcon size={12} aria-hidden="true" />{tag.name}</span>)}</span></td><td>{formatBytes(file.byte_size)}</td><td>{formatDate(file.updated_at)}</td><td><button className="icon-button icon-button--small" type="button" onClick={() => deleteMutation.mutate(file)} aria-label={`移入回收站 ${file.display_name}`} title="移入回收站"><MoreHorizontal size={16} aria-hidden="true" /></button></td></tr>)}</tbody></table>
            {filesQuery.isLoading && <div className="empty-state"><strong>正在加载文件…</strong></div>}
            {filesQuery.isError && <div className="empty-state"><strong>文件加载失败</strong><span>{filesQuery.error instanceof Error ? filesQuery.error.message : '请稍后重试。'}</span><button type="button" className="quiet-button" onClick={() => void filesQuery.refetch()}>重试</button></div>}
            {!filesQuery.isLoading && !filesQuery.isError && files.length === 0 && <div className="empty-state"><FileUp size={24} aria-hidden="true" /><strong>{query || folderId || tagId || documentType || status ? '没有匹配的文件' : '还没有文件'}</strong><span>{query || folderId || tagId || documentType || status ? '尝试清除搜索和筛选条件。' : '导入 PDF、DOCX、PPTX、TXT 或 Markdown 开始整理。'}</span><button type="button" className="primary-button" onClick={() => inputRef.current?.click()}>导入文件</button></div>}
          </div>
          {uploadMutation.isPending && <div className="inline-progress">正在校验并复制文件…</div>}
          {uploadMutation.isError && <div className="inline-error">{uploadMutation.error instanceof Error ? uploadMutation.error.message : '导入失败，请稍后重试。'}</div>}
          {tags.length > 0 && <div className="tag-hint"><TagIcon size={15} aria-hidden="true" />已创建 {tags.length} 个标签，可在文件详情中编辑。</div>}
        </div>
      </div>
      {versionConflict && <div className="inline-error" role="alert"><span>{versionConflict}</span><button type="button" className="quiet-button" onClick={() => { setVersionConflict(null); void queryClient.invalidateQueries({ queryKey: ['folders'] }); void queryClient.invalidateQueries({ queryKey: ['files'] }) }}>重新加载</button></div>}
    </section>
  )
}

function FileTextGlyph({ type }: { type: string }) {
  return <span className={`file-type-glyph file-type-glyph--${type.toLowerCase()}`} aria-hidden="true">{type === 'MARKDOWN' ? 'M' : type.slice(0, 1)}</span>
}
