import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen, Save } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { createKnowledgeBase } from '../api/knowledgeBases'

export default function KnowledgeBaseNewPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState('#176b87')
  const mutation = useMutation({
    mutationFn: createKnowledgeBase,
    onSuccess: (item) => {
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      void navigate(`/knowledge-bases/${item.knowledge_base_id}`)
    },
  })
  const submit = (event: FormEvent) => {
    event.preventDefault()
    mutation.mutate({ name, description: description || null, icon: 'book-open', color })
  }

  return <section className="detail-page"><Link className="back-link" to="/knowledge-bases"><ArrowLeft size={16} aria-hidden="true" />返回知识库</Link><div className="detail-heading"><div><span className="eyebrow">新建本地资料空间</span><h1>新建知识库</h1><p>先建立空知识库；添加文件和索引将在下一批开放。</p></div></div><form className="knowledge-form detail-section" onSubmit={submit}><div className="knowledge-form__mark" style={{ backgroundColor: color }}><BookOpen size={24} aria-hidden="true" /></div><label>名称<input aria-label="知识库名称" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} autoFocus /></label><label>描述<textarea aria-label="知识库描述" maxLength={2000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} /></label><label>颜色<input aria-label="知识库颜色" type="color" value={color} onChange={(event) => setColor(event.target.value)} /></label>{mutation.isError && <div className="inline-error" role="alert">{mutation.error instanceof Error ? mutation.error.message : '创建失败，请重试。'}</div>}<div className="heading-actions"><button className="primary-button" type="submit" disabled={mutation.isPending || !name.trim()}><Save size={16} aria-hidden="true" />{mutation.isPending ? '正在创建' : '创建知识库'}</button><Link className="quiet-button" to="/knowledge-bases">取消</Link></div></form></section>
}
