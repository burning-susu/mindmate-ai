import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen, Save, Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { apiRequest } from '../api/client'
import { isVersionConflict } from '../api/files'
import { trashKnowledgeBase, updateKnowledgeBase, type KnowledgeBaseItem } from '../api/knowledgeBases'

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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      void queryClient.invalidateQueries({ queryKey: ['trash-knowledge-bases'] })
      void navigate('/knowledge-bases')
    },
    onError: (error) => setConflict(isVersionConflict(error)),
  })
  const submit = (event: FormEvent) => { event.preventDefault(); setConflict(false); updateMutation.mutate() }
  return <><div className="detail-heading"><div className="knowledge-title"><div className="knowledge-mark knowledge-mark--large" style={{ backgroundColor: color }}><BookOpen size={24} aria-hidden="true" /></div><div><span className="eyebrow">{item.status === 'EMPTY' ? '空知识库' : item.status}</span><h1>{item.name}</h1><p>{item.file_count} 个文件 · 版本 {item.row_version}</p></div></div><button className="danger-button" type="button" onClick={() => { if (window.confirm(`将知识库“${item.name}”移入回收站？原始文件不会被删除。`)) trashMutation.mutate() }}><Trash2 size={16} aria-hidden="true" />移入回收站</button></div>{conflict && <div className="inline-error" role="alert"><span>知识库已被其他操作修改，请重新加载后再试。</span><button className="quiet-button" type="button" onClick={() => window.location.reload()}>重新加载</button></div>}<div className="detail-grid"><form className="knowledge-form detail-section" onSubmit={submit}><h2>基本信息</h2><label>名称<input aria-label="知识库名称" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} /></label><label>描述<textarea aria-label="知识库描述" maxLength={2000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} /></label><label>颜色<input aria-label="知识库颜色" type="color" value={color} onChange={(event) => setColor(event.target.value)} /></label>{updateMutation.isError && !conflict && <div className="inline-error" role="alert">{updateMutation.error instanceof Error ? updateMutation.error.message : '保存失败。'}</div>}<button className="primary-button" type="submit" disabled={updateMutation.isPending}><Save size={16} aria-hidden="true" />{updateMutation.isPending ? '正在保存' : '保存更改'}</button></form><section className="detail-section"><h2>资料与索引</h2><div className="detail-empty"><BookOpen size={22} aria-hidden="true" /><span>添加文件与持久索引任务将在下一批开放。</span></div></section></div></>
}

export default function KnowledgeBaseDetailPage() {
  const { knowledgeBaseId = '' } = useParams()
  const query = useQuery({ queryKey: ['knowledge-base', knowledgeBaseId], queryFn: () => apiRequest<KnowledgeBaseItem>(`/api/v1/knowledge-bases/${knowledgeBaseId}`), enabled: Boolean(knowledgeBaseId) })
  if (query.isLoading) return <section className="detail-page"><h1>正在加载知识库…</h1></section>
  if (query.isError || !query.data) return <section className="detail-page"><Link className="back-link" to="/knowledge-bases"><ArrowLeft size={16} aria-hidden="true" />返回知识库</Link><h1>知识库加载失败</h1><p>{query.error instanceof Error ? query.error.message : '知识库不存在。'}</p><button className="quiet-button" type="button" onClick={() => void query.refetch()}>重试</button></section>
  return <section className="detail-page"><Link className="back-link" to="/knowledge-bases"><ArrowLeft size={16} aria-hidden="true" />返回知识库</Link><DetailForm key={query.data.row_version} item={query.data} /></section>
}
