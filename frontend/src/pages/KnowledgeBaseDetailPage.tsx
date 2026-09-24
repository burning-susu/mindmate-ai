import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen, FilePlus2, RefreshCw, Save, Trash2, X } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { apiRequest } from '../api/client'
import { isVersionConflict, type FileListResponse } from '../api/files'
import KnowledgeBaseRetrievalPanel from '../components/KnowledgeBaseRetrievalPanel'
import {
  addKnowledgeBaseMembers,
  getKnowledgeMembershipTask,
  listKnowledgeBaseMembers,
  removeKnowledgeBaseMember,
  trashKnowledgeBase,
  updateKnowledgeBase,
  type KnowledgeBaseItem,
} from '../api/knowledgeBases'

const fileStatusLabels: Record<string, string> = {
  PARSED: '已解析',
  QUEUED: '等待解析',
  PARSING: '正在解析',
  PARSE_FAILED: '解析失败',
  IN_TRASH: '回收站',
}

function knowledgeBaseStatusLabel(status: string) {
  if (status === 'EMPTY') return '空知识库'
  if (status === 'PREPARING') return '成员待索引'
  if (status === 'PARTIAL') return '部分资料可用'
  if (status === 'READY') return '索引就绪'
  return status
}

function knowledgeBaseStatusClass(status: string) {
  if (status === 'READY' || status === 'PARTIAL') return 'file-status--ready'
  return 'file-status--queued'
}

function knowledgeBaseMemberDescription(status: string) {
  if (status === 'READY') return '当前知识库已有活动索引，可查看本地候选检索结果。'
  if (status === 'PARTIAL') return '部分成员已进入活动索引，其余文件仍会保留真实不可用状态。'
  return '成员加入后仍需建立索引；当前知识库问答不可用。'
}

function taskResultText(result: Record<string, unknown>) {
  const name = typeof result.display_name === 'string' ? result.display_name : String(result.file_id ?? '未知文件')
  const message = typeof result.message === 'string' ? result.message : '处理完成。'
  return `${name}：${message}`
}

function MemberManager({ item }: { item: KnowledgeBaseItem }) {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<string[]>([])
  const [taskId, setTaskId] = useState<string | null>(null)
  const membersQuery = useQuery({
    queryKey: ['knowledge-base-members', item.knowledge_base_id],
    queryFn: () => listKnowledgeBaseMembers(item.knowledge_base_id),
  })
  const filesQuery = useQuery({
    queryKey: ['knowledge-member-file-options', item.knowledge_base_id],
    queryFn: () => apiRequest<FileListResponse>('/api/v1/files?sort=name'),
    staleTime: 0,
  })
  const taskQuery = useQuery({
    queryKey: ['knowledge-membership-task', taskId],
    queryFn: () => getKnowledgeMembershipTask(taskId ?? ''),
    enabled: Boolean(taskId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && ['COMPLETED', 'FAILED', 'CANCELLED'].includes(status) ? false : 150
    },
  })

  useEffect(() => {
    const task = taskQuery.data
    if (!task || !['COMPLETED', 'FAILED', 'CANCELLED'].includes(task.status)) return
    void queryClient.invalidateQueries({ queryKey: ['knowledge-base-members', item.knowledge_base_id] })
    void queryClient.invalidateQueries({ queryKey: ['knowledge-base', item.knowledge_base_id] })
    void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
  }, [item.knowledge_base_id, queryClient, taskQuery.data])

  const memberIds = useMemo(
    () => new Set(membersQuery.data?.items?.map((member) => member.file_id) ?? []),
    [membersQuery.data],
  )
  const candidates = filesQuery.data?.items?.filter((file) => !memberIds.has(file.file_id)) ?? []
  const addMutation = useMutation({
    mutationFn: () => addKnowledgeBaseMembers(item.knowledge_base_id, selected),
    onSuccess: (task) => { setSelected([]); setTaskId(task.task_id) },
  })
  const removeMutation = useMutation({
    mutationFn: (fileId: string) => removeKnowledgeBaseMember(item.knowledge_base_id, fileId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['knowledge-base-members', item.knowledge_base_id] })
      void queryClient.invalidateQueries({ queryKey: ['knowledge-base', item.knowledge_base_id] })
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
    },
  })
  const activeTask = taskQuery.data ?? addMutation.data ?? null
  const taskRunning = Boolean(activeTask && !['COMPLETED', 'FAILED', 'CANCELLED'].includes(activeTask.status))
  const results = (activeTask?.results ?? []) as Array<Record<string, unknown>>

  return <section className="detail-section knowledge-members"><div className="section-heading"><div><h2>资料成员</h2><p>{knowledgeBaseMemberDescription(item.status)}</p></div><span className={`file-status ${knowledgeBaseStatusClass(item.status)}`}>{knowledgeBaseStatusLabel(item.status)}</span></div>
    {membersQuery.isLoading && <div className="detail-empty"><RefreshCw size={20} aria-hidden="true" />正在加载成员</div>}
    {membersQuery.isError && <div className="inline-error" role="alert">成员加载失败。<button className="quiet-button" type="button" onClick={() => void membersQuery.refetch()}>重试</button></div>}
    {(membersQuery.data?.items?.length ?? 0) === 0 && !membersQuery.isLoading && <div className="detail-empty"><BookOpen size={22} aria-hidden="true" /><span>尚未加入任何文件。</span></div>}
    {(membersQuery.data?.items?.length ?? 0) > 0 && <div className="member-list">{membersQuery.data?.items?.map((member) => <div className="member-row" key={member.file_id}><div className="member-row__main"><strong>{member.display_name}</strong><span>{member.document_type} · {fileStatusLabels[member.file_status] ?? member.file_status}</span></div><div className="member-row__state"><span className="file-status file-status--queued">{member.index_state === 'PENDING' ? '待建立索引' : member.index_state}</span><small>{member.unavailable_reason}</small></div><button className="icon-button" type="button" title="移出知识库" aria-label={`移出知识库 ${member.display_name}`} disabled={removeMutation.isPending} onClick={() => removeMutation.mutate(member.file_id)}><X size={16} aria-hidden="true" /></button></div>)}</div>}

    <div className="member-picker"><div className="section-heading"><div><h3>添加已导入文件</h3><p>可批量选择；解析中或解析失败的文件会保留真实不可用状态。</p></div><button className="primary-button" type="button" disabled={selected.length === 0 || addMutation.isPending || taskRunning} onClick={() => addMutation.mutate()}><FilePlus2 size={16} aria-hidden="true" />加入 {selected.length > 0 ? `${selected.length} 个` : ''}</button></div>
      {filesQuery.isLoading && <span className="member-picker__hint">正在加载文件…</span>}
      {!filesQuery.isLoading && candidates.length === 0 && <span className="member-picker__hint">没有可添加的已导入文件。</span>}
      <div className="member-options">{candidates.map((file) => <label key={file.file_id}><input type="checkbox" checked={selected.includes(file.file_id)} onChange={() => setSelected((current) => current.includes(file.file_id) ? current.filter((id) => id !== file.file_id) : [...current, file.file_id])} /><span><strong>{file.display_name}</strong><small>{file.document_type} · {fileStatusLabels[file.status] ?? file.status}</small></span></label>)}</div>
    </div>
    {activeTask && <div className="task-summary" role="status"><strong>{['COMPLETED', 'FAILED', 'CANCELLED'].includes(activeTask.status) ? '成员准入任务已结束' : '正在持久化成员关系'}</strong><span>{activeTask.progress ?? 0}% · {activeTask.status}</span><small>成员准入完成不代表索引可用。</small></div>}
    {addMutation.isError && <div className="inline-error" role="alert">{addMutation.error instanceof Error ? addMutation.error.message : '提交失败。'}</div>}
    {removeMutation.isError && <div className="inline-error" role="alert">{removeMutation.error instanceof Error ? removeMutation.error.message : '移出失败。'}</div>}
    {results.length > 0 && <div className="task-results" aria-label="成员任务结果">{results.map((result, index) => <div className={result.status === 'FAILED' ? 'task-result task-result--failed' : 'task-result'} key={`${String(result.file_id)}-${index}`}>{taskResultText(result)}</div>)}</div>}
  </section>
}

function DetailForm({ item }: { item: KnowledgeBaseItem }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [name, setName] = useState(item.name)
  const [description, setDescription] = useState(item.description ?? '')
  const [color, setColor] = useState(item.color ?? '#176b87')
  const [conflict, setConflict] = useState(false)
  const updateMutation = useMutation({
    mutationFn: () => updateKnowledgeBase(item.knowledge_base_id, item.row_version, { name, description: description || null, icon: item.icon ?? 'book-open', color }),
    onSuccess: (updated) => queryClient.setQueryData(['knowledge-base', item.knowledge_base_id], updated),
    onError: (error) => setConflict(isVersionConflict(error)),
  })
  const trashMutation = useMutation({
    mutationFn: () => trashKnowledgeBase(item),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] }); void queryClient.invalidateQueries({ queryKey: ['trash-knowledge-bases'] }); void navigate('/knowledge-bases') },
    onError: (error) => setConflict(isVersionConflict(error)),
  })
  const submit = (event: FormEvent) => { event.preventDefault(); setConflict(false); updateMutation.mutate() }
  return <><div className="detail-heading"><div className="knowledge-title"><div className="knowledge-mark knowledge-mark--large" style={{ backgroundColor: color }}><BookOpen size={24} aria-hidden="true" /></div><div><span className="eyebrow">{knowledgeBaseStatusLabel(item.status)}</span><h1>{item.name}</h1><p>{item.file_count} 个文件 · 版本 {item.row_version}</p></div></div><button className="danger-button" type="button" onClick={() => { if (window.confirm(`将知识库“${item.name}”移入回收站？原始文件不会被删除。`)) trashMutation.mutate() }}><Trash2 size={16} aria-hidden="true" />移入回收站</button></div>{conflict && <div className="inline-error" role="alert"><span>知识库已被其他操作修改，请重新加载后再试。</span><button className="quiet-button" type="button" onClick={() => window.location.reload()}>重新加载</button></div>}<div className="detail-grid"><form className="knowledge-form detail-section" onSubmit={submit}><h2>基本信息</h2><label>名称<input aria-label="知识库名称" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} /></label><label>描述<textarea aria-label="知识库描述" maxLength={2000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} /></label><label>颜色<input aria-label="知识库颜色" type="color" value={color} onChange={(event) => setColor(event.target.value)} /></label>{updateMutation.isError && !conflict && <div className="inline-error" role="alert">{updateMutation.error instanceof Error ? updateMutation.error.message : '保存失败。'}</div>}<button className="primary-button" type="submit" disabled={updateMutation.isPending}><Save size={16} aria-hidden="true" />{updateMutation.isPending ? '正在保存' : '保存更改'}</button></form><MemberManager item={item} /></div><KnowledgeBaseRetrievalPanel key={item.knowledge_base_id} item={item} /></>
}

export default function KnowledgeBaseDetailPage() {
  const { knowledgeBaseId = '' } = useParams()
  const query = useQuery({ queryKey: ['knowledge-base', knowledgeBaseId], queryFn: () => apiRequest<KnowledgeBaseItem>(`/api/v1/knowledge-bases/${knowledgeBaseId}`), enabled: Boolean(knowledgeBaseId) })
  if (query.isLoading) return <section className="detail-page"><h1>正在加载知识库…</h1></section>
  if (query.isError || !query.data) return <section className="detail-page"><Link className="back-link" to="/knowledge-bases"><ArrowLeft size={16} aria-hidden="true" />返回知识库</Link><h1>知识库加载失败</h1><p>{query.error instanceof Error ? query.error.message : '知识库不存在。'}</p><button className="quiet-button" type="button" onClick={() => void query.refetch()}>重试</button></section>
  return <section className="detail-page"><Link className="back-link" to="/knowledge-bases"><ArrowLeft size={16} aria-hidden="true" />返回知识库</Link><DetailForm key={query.data.row_version} item={query.data} /></section>
}
