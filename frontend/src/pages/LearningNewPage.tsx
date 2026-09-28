import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { type FormEvent, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { v7 as uuidv7 } from 'uuid'

import { ApiError, apiRequest } from '../api/client'
import { createLearningSession, getLearningProviderPlan } from '../api/learning'
import { listKnowledgeBaseMembers, type KnowledgeBaseItem, type KnowledgeBaseListResponse } from '../api/knowledgeBases'

const MOCK_BANNER = '新建学习会话使用当前选择。Mock 仍按本地规则出题和评分，不会外发。在线模式每道题和每次点评前都会单独确认费用。已经创建的会话保持创建时的服务。这仍不是完整学习计划或复习。'

export default function LearningNewPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const knowledgeBaseId = searchParams.get('knowledge_base_id')?.trim() ?? ''
  const [topic, setTopic] = useState('')
  const [goalText, setGoalText] = useState('')
  const [targetQuestionCount, setTargetQuestionCount] = useState(1)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [chargeConfirmed, setChargeConfirmed] = useState(false)
  const clientRequestId = useRef<string | null>(null)
  const submitLock = useRef(false)
  const knowledgeBaseQuery = useQuery({
    queryKey: ['knowledge-base', knowledgeBaseId],
    queryFn: () => apiRequest<KnowledgeBaseItem>(`/api/v1/knowledge-bases/${knowledgeBaseId}`),
    enabled: Boolean(knowledgeBaseId),
  })
  const knowledgeBaseListQuery = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: () => apiRequest<KnowledgeBaseListResponse>('/api/v1/knowledge-bases'),
    enabled: !knowledgeBaseId,
    retry: false,
  })
  const readyChoices = (knowledgeBaseListQuery.data?.items ?? []).filter((item) => item.status === 'READY' && item.available_file_count > 0)
  const membersQuery = useQuery({
    queryKey: ['knowledge-base-members', knowledgeBaseId],
    queryFn: () => listKnowledgeBaseMembers(knowledgeBaseId),
    enabled: Boolean(knowledgeBaseId),
  })
  const knowledgeBase = knowledgeBaseQuery.data
  const ready = knowledgeBase?.status === 'READY' && knowledgeBase.available_file_count > 0
  const planQuery = useQuery({
    queryKey: ['learning-provider-plan'],
    queryFn: getLearningProviderPlan,
    retry: false,
  })
  const online = planQuery.data?.requires_charge_confirmation === true
  const topicError = topic.trim().length === 0
    ? '请输入学习主题。'
    : topic.trim().length > 80
      ? '学习主题不能超过 80 个字符。'
      : ''
  const goalError = goalText.trim().length === 0
    ? '请输入学习目标。'
    : goalText.trim().length > 200
      ? '学习目标不能超过 200 个字符。'
      : ''
  const topicReady = !topicError
  const goalReady = !goalError
  const canSubmit = Boolean(knowledgeBaseId)
    && ready
    && topicReady
    && goalReady
    && !knowledgeBaseQuery.isLoading
    && !membersQuery.isLoading
    && !planQuery.isLoading
    && !submitting
    && (!online || (chargeConfirmed && !planQuery.data?.budget_blocks))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!canSubmit || submitLock.current) return
    submitLock.current = true
    setSubmitting(true)
    setError('')
    if (!clientRequestId.current) clientRequestId.current = uuidv7()
    try {
      const created = await createLearningSession(
        {
          knowledgeBaseId,
          topic: topic.trim(),
          goalText: goalText.trim(),
          targetQuestionCount,
          confirmProviderCharge: online && chargeConfirmed,
        },
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
          <h1>基于知识库的逐题练习</h1>
          <p>打开本页不会创建学习会话。每次只展示一道单选题。</p>
        </div>
      </div>
      {!knowledgeBaseId && (
        <div className="learning-kb-choices detail-section">
          <h2>选择知识库</h2>
          <p>只列出索引就绪且有可用文件的知识库。打开或选择都不会创建题目。</p>
          {knowledgeBaseListQuery.isLoading ? <p role="status">正在读取知识库…</p> : null}
          {knowledgeBaseListQuery.isError ? (
            <div className="inline-error" role="alert">
              <span>{knowledgeBaseListQuery.error instanceof Error ? knowledgeBaseListQuery.error.message : '知识库列表读取失败。'}</span>
              <button className="quiet-button" type="button" onClick={() => void knowledgeBaseListQuery.refetch()}>重新读取</button>
            </div>
          ) : null}
          {!knowledgeBaseListQuery.isLoading && !knowledgeBaseListQuery.isError && readyChoices.length > 0 ? (
            <ul aria-label="可选知识库">
              {readyChoices.map((item) => (
                <li key={item.knowledge_base_id}>
                  <Link className="quiet-button" to={`/learning/new?knowledge_base_id=${encodeURIComponent(item.knowledge_base_id)}`}>{item.name}</Link>
                </li>
              ))}
            </ul>
          ) : null}
          {!knowledgeBaseListQuery.isLoading && !knowledgeBaseListQuery.isError && readyChoices.length === 0 ? (
            <div role="status">
              <p>还没有索引就绪、并且有可用文件的知识库。请先导入文件，加入知识库并完成索引。这里不会创建题目。</p>
              <div className="home-continue__actions">
                <Link className="quiet-button" to="/files">导入文件</Link>
                <Link className="quiet-button" to="/knowledge-bases">知识库</Link>
              </div>
            </div>
          ) : null}
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
              {(membersQuery.data.items ?? []).map((member) => (
                <li key={member.file_id}>
                  <span>{member.display_name}</span>
                  {!member.available_for_retrieval && (
                    <span className="learning-scope-list__status">
                      不可用：{member.unavailable_reason ?? '当前资料不可用于检索'}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {!ready && <div className="inline-error" role="alert">当前知识库没有可用索引或可用文件，不能开始学习。</div>}
          <label>学习主题
            <input
              aria-label="学习主题"
              aria-describedby="learning-topic-error"
              aria-invalid={Boolean(topicError)}
              maxLength={80}
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
            />
            {topicError && <span className="field-error" id="learning-topic-error" role="alert">{topicError}</span>}
          </label>
          <label>学习目标
            <textarea
              aria-label="学习目标"
              aria-describedby="learning-goal-error"
              aria-invalid={Boolean(goalError)}
              maxLength={200}
              rows={3}
              value={goalText}
              onChange={(event) => setGoalText(event.target.value)}
            />
            {goalError && <span className="field-error" id="learning-goal-error" role="alert">{goalError}</span>}
          </label>
          <label>计划题数
            <select
              aria-label="计划题数"
              value={targetQuestionCount}
              onChange={(event) => setTargetQuestionCount(Number(event.target.value))}
            >
              {[1, 2, 3, 4, 5].map((count) => <option key={count} value={count}>{count} 题</option>)}
            </select>
          </label>
          {planQuery.data ? <p role="status">{planQuery.data.outbound_summary}</p> : null}
          {online && planQuery.data ? (
            <div className="settings-privacy-copy">
              {planQuery.data.budget_notice ? <p role="alert">{planQuery.data.budget_notice}</p> : null}
              <p>
                将向 {planQuery.data.provider} 发送学习主题、学习目标和至多 2 段服务端批准的资料摘录。
                请求模型 {planQuery.data.requested_model}。按 {planQuery.data.question_estimate.checked_on} 公开费率，
                用满本地上限时出题粗估不超过 {planQuery.data.question_estimate.estimated_usd_ceiling} 美元。
                {planQuery.data.question_estimate.disclaimer}
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={chargeConfirmed}
                  onChange={(event) => setChargeConfirmed(event.target.checked)}
                />
                我确认本次向 {planQuery.data.provider} 出题可能产生费用
              </label>
            </div>
          ) : null}
          {error && <div className="inline-error" role="alert">{error}</div>}
          <button className="primary-button" type="submit" disabled={!canSubmit} aria-busy={submitting}>
            {submitting ? '正在创建' : '创建并开始'}
          </button>
        </form>
      )}
    </section>
  )
}
