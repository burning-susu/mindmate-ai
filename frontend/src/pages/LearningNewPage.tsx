import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { type FormEvent, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { v7 as uuidv7 } from 'uuid'

import { ApiError, apiRequest } from '../api/client'
import { createLearningSession } from '../api/learning'
import { listKnowledgeBaseMembers, type KnowledgeBaseItem } from '../api/knowledgeBases'

const MOCK_BANNER = '本地规则模拟演示，未调用真实 DeepSeek。学习出题不读取聊天设置里的在线模式。'

export default function LearningNewPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const knowledgeBaseId = searchParams.get('knowledge_base_id')?.trim() ?? ''
  const [topic, setTopic] = useState('')
  const [goalText, setGoalText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const clientRequestId = useRef<string | null>(null)
  const submitLock = useRef(false)
  const knowledgeBaseQuery = useQuery({
    queryKey: ['knowledge-base', knowledgeBaseId],
    queryFn: () => apiRequest<KnowledgeBaseItem>(`/api/v1/knowledge-bases/${knowledgeBaseId}`),
    enabled: Boolean(knowledgeBaseId),
  })
  const membersQuery = useQuery({
    queryKey: ['knowledge-base-members', knowledgeBaseId],
    queryFn: () => listKnowledgeBaseMembers(knowledgeBaseId),
    enabled: Boolean(knowledgeBaseId),
  })
  const knowledgeBase = knowledgeBaseQuery.data
  const ready = knowledgeBase?.status === 'READY' && knowledgeBase.available_file_count > 0
  const topicReady = topic.trim().length > 0 && topic.trim().length <= 80
  const goalReady = goalText.trim().length > 0 && goalText.trim().length <= 200
  const canSubmit = Boolean(knowledgeBaseId) && ready && topicReady && goalReady && !knowledgeBaseQuery.isLoading && !membersQuery.isLoading && !submitting

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!canSubmit || submitLock.current) return
    submitLock.current = true
    setSubmitting(true)
    setError('')
    if (!clientRequestId.current) clientRequestId.current = uuidv7()
    try {
      const created = await createLearningSession(
        { knowledgeBaseId, topic: topic.trim(), goalText: goalText.trim() },
        clientRequestId.current,
      )
      navigate(`/learning/session/${created.learning_session_id}`)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.problem.detail : '创建结果未知。再次提交会使用同一次请求，不会另开学习会话。')
      submitLock.current = false
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-page learning-page">
      <div className="detail-heading__actions">
        <Link className="back-link" to={knowledgeBaseId ? `/knowledge-bases/${knowledgeBaseId}` : '/knowledge-bases'}>
          <ArrowLeft size={16} aria-hidden="true" />返回知识库
        </Link>
        <Link className="quiet-button" to="/history?tab=learning">学习历史</Link>
      </div>
      <p className="learning-mock-banner" role="status">{MOCK_BANNER}</p>
      <div className="detail-heading">
        <div>
          <span className="eyebrow">开始学习</span>
          <h1>基于知识库的一题演示</h1>
          <p>打开本页不会创建学习会话。演示题量固定为 1，不提供难度、题型或题量切换。</p>
        </div>
      </div>
      {!knowledgeBaseId && (
        <div className="inline-error" role="alert">
          <span>请从已索引就绪的知识库进入。</span>
          <Link className="quiet-button" to="/knowledge-bases">前往知识库</Link>
        </div>
      )}
      {knowledgeBaseId && knowledgeBaseQuery.isLoading && <p>正在读取知识库…</p>}
      {knowledgeBaseId && knowledgeBaseQuery.isError && (
        <div className="inline-error" role="alert">
          <span>{knowledgeBaseQuery.error instanceof Error ? knowledgeBaseQuery.error.message : '知识库读取失败。'}</span>
          <button className="quiet-button" type="button" onClick={() => void knowledgeBaseQuery.refetch()}>重新读取</button>
        </div>
      )}
      {knowledgeBase && (
        <form className="knowledge-form detail-section" onSubmit={submit}>
          <h2>资料范围</h2>
          <p>{knowledgeBase.name} · {knowledgeBase.status === 'READY' ? '索引就绪' : knowledgeBase.status} · 可用文件 {knowledgeBase.available_file_count}</p>
          {membersQuery.isLoading && <p>正在读取成员…</p>}
          {membersQuery.isError && (
            <div className="inline-error" role="alert">
              <span>资料成员读取失败。</span>
              <button className="quiet-button" type="button" onClick={() => void membersQuery.refetch()}>重新读取</button>
            </div>
          )}
          {membersQuery.data && (
            <ul className="learning-scope-list" aria-label="已选资料">
              {membersQuery.data.items.map((member) => <li key={member.file_id}>{member.display_name}</li>)}
            </ul>
          )}
          {!ready && <div className="inline-error" role="alert">当前知识库没有可用索引或可用文件，不能开始学习。</div>}
          <label>学习主题
            <input aria-label="学习主题" maxLength={80} value={topic} onChange={(event) => setTopic(event.target.value)} />
          </label>
          <label>学习目标
            <textarea aria-label="学习目标" maxLength={200} rows={3} value={goalText} onChange={(event) => setGoalText(event.target.value)} />
          </label>
          <p>题量：1。题型由服务端生成为单选题。难度和题量不能在这里调整。</p>
          {error && <div className="inline-error" role="alert">{error}</div>}
          <button className="primary-button" type="submit" disabled={!canSubmit} aria-busy={submitting}>
            {submitting ? '正在创建' : '创建并开始'}
          </button>
        </form>
      )}
    </section>
  )
}
