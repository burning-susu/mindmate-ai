import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { v7 as uuidv7 } from 'uuid'

import { ApiError, apiRequest } from '../api/client'
import {
  getLearningSession,
  submitLearningAttempt,
  type LearningCitation,
  type LearningFeedback,
  type LearningSession,
} from '../api/learning'
import { type KnowledgeBaseItem } from '../api/knowledgeBases'
import { CitedText, SourceCitationPanel } from '../components/SourceCitationPanel'

const MOCK_BANNER = '本地规则模拟演示，未调用真实 DeepSeek。学习出题不读取聊天设置里的在线模式。'

function resultLabel(result: string) {
  if (result === 'CORRECT') return '正确'
  if (result === 'INCORRECT') return '不正确'
  return result
}

function canRevise(session: LearningSession) {
  const code = session.status === 'SOURCE_INVALID' ? 'SOURCE_INVALID' : session.failure_code
  return code === 'EVIDENCE_INSUFFICIENT' || code === 'CANNOT_FORM_RELIABLE_QUESTION'
}

function blocksAnswer(session: LearningSession) {
  return session.status === 'FAILED' || session.status === 'SOURCE_INVALID' || Boolean(session.failure_code && !session.question)
}

export default function LearningSessionPage() {
  const { sessionId = '' } = useParams()
  const queryClient = useQueryClient()
  const sessionQuery = useQuery({
    queryKey: ['learning-session', sessionId],
    queryFn: () => getLearningSession(sessionId),
    enabled: Boolean(sessionId),
    staleTime: 0,
    refetchOnMount: 'always',
    retry: false,
  })
  const session = sessionQuery.data
  const knowledgeBaseQuery = useQuery({
    queryKey: ['knowledge-base', session?.knowledge_base_id],
    queryFn: () => apiRequest<KnowledgeBaseItem>(`/api/v1/knowledge-bases/${session?.knowledge_base_id}`),
    enabled: Boolean(session?.knowledge_base_id),
  })
  const [selectedOption, setSelectedOption] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [pendingFeedback, setPendingFeedback] = useState<LearningFeedback | null>(null)
  const [selectedCitation, setSelectedCitation] = useState<LearningCitation | null>(null)
  const clientRequestId = useRef<string | null>(null)
  const submitLock = useRef(false)
  const question = session?.question ?? null
  const feedback = question?.feedback ?? pendingFeedback
  const answered = Boolean(feedback)
  const blocked = session ? blocksAnswer(session) && !answered : false

  const refreshSession = async () => {
    const latest = await getLearningSession(sessionId)
    queryClient.setQueryData(['learning-session', sessionId], latest)
    return latest
  }

  const submit = async () => {
    if (!question || !selectedOption || answered || blocked || submitLock.current) return
    submitLock.current = true
    setSubmitting(true)
    setSubmitError('')
    if (!clientRequestId.current) clientRequestId.current = uuidv7()
    const requestId = clientRequestId.current
    try {
      const result = await submitLearningAttempt(
        question.question_id,
        { selectedOption, expectedQuestionVersion: question.row_version },
        requestId,
      )
      setPendingFeedback(result)
      try {
        await refreshSession()
      } catch {
        setSubmitError('反馈已返回，刷新会话失败。可以重新读取。')
      }
    } catch (caught) {
      try {
        const latest = await refreshSession()
        if (latest.question?.feedback) {
          setPendingFeedback(null)
          setSubmitError('')
          return
        }
      } catch {
        setSubmitError('提交结果未知，暂时读不到服务端状态。请稍后重新读取，不要更换本次请求。')
        submitLock.current = false
        setSubmitting(false)
        return
      }
      if (caught instanceof ApiError && (caught.problem.code === 'ANSWER_LOCKED' || caught.status === 412)) {
        setSubmitError(caught.problem.detail)
      } else if (caught instanceof ApiError) {
        setSubmitError(caught.problem.detail)
      } else {
        setSubmitError('提交结果未知。已核对服务端，这次作答尚未保存。再次提交会使用同一次请求。')
      }
      submitLock.current = false
    } finally {
      setSubmitting(false)
    }
  }

  if (sessionQuery.isLoading) {
    return <section className="detail-page learning-page"><p role="status">正在读取学习会话…</p></section>
  }
  if (sessionQuery.isError || !session) {
    return (
      <section className="detail-page learning-page">
        <p className="learning-mock-banner" role="status">{MOCK_BANNER}</p>
        <div className="inline-error" role="alert">
          <span>{sessionQuery.error instanceof Error ? sessionQuery.error.message : '学习会话读取失败。'}</span>
          <button className="quiet-button" type="button" onClick={() => void sessionQuery.refetch()}>重新读取</button>
          <Link className="quiet-button" to="/knowledge-bases">返回知识库</Link>
        </div>
      </section>
    )
  }

  const selectedLabel = question?.options.find((option) => option.option_id === (feedback?.selected_option ?? selectedOption))?.label
  const knowledgeBaseName = knowledgeBaseQuery.data?.name ?? session.knowledge_base_id

  return (
    <section className="detail-page learning-page">
      <Link className="back-link" to={`/knowledge-bases/${session.knowledge_base_id}`}>
        <ArrowLeft size={16} aria-hidden="true" />返回知识库
      </Link>
      <p className="learning-mock-banner" role="status">{MOCK_BANNER}</p>
      <div className="detail-heading">
        <div>
          <span className="eyebrow">学习会话</span>
          <h1>{session.topic}</h1>
          <p>目标：{session.goal_text}</p>
          <p>资料范围：{knowledgeBaseName} · {session.scope?.file_ids.length ?? 0} 个文件 · 题量 {session.target_question_count}</p>
          {session.plan?.knowledge_point_title && <p>知识点：{session.plan.knowledge_point_title}</p>}
          <p>模型 {session.model} · live_model_called={String(session.live_model_called)}</p>
        </div>
      </div>
      {(session.status === 'FAILED' || session.status === 'SOURCE_INVALID') && (
        <div className="inline-error" role="alert">
          <span>{session.failure_detail || '这次学习不能继续。'}</span>
          {canRevise(session) && (
            <Link className="quiet-button" to={`/learning/new?knowledge_base_id=${encodeURIComponent(session.knowledge_base_id)}`}>返回修改主题</Link>
          )}
          <Link className="quiet-button" to={`/knowledge-bases/${session.knowledge_base_id}`}>返回知识库</Link>
        </div>
      )}
      {question && !blocked && (
        <div className="detail-section learning-question">
          <h2>第 {question.sequence_number} 题</h2>
          <fieldset disabled={answered || submitting}>
            <legend>{question.prompt_text}</legend>
            {question.options.map((option) => (
              <label key={option.option_id}>
                <input
                  type="radio"
                  name={`learning-${question.question_id}`}
                  value={option.option_id}
                  checked={(feedback?.selected_option ?? selectedOption) === option.option_id}
                  onChange={() => setSelectedOption(option.option_id)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>
          {!answered && (
            <button className="primary-button" type="button" disabled={!selectedOption || submitting} aria-busy={submitting} onClick={() => void submit()}>
              {submitting ? '正在提交' : '提交答案'}
            </button>
          )}
          {submitting && <p role="status">正在提交，请等待服务端结果。</p>}
          {submitError && (
            <div className="inline-error" role="alert">
              <span>{submitError}</span>
              <button className="quiet-button" type="button" onClick={() => void refreshSession().catch(() => setSubmitError('重新读取失败。'))}>重新读取</button>
            </div>
          )}
          {answered && feedback && (
            <div className="learning-feedback" aria-label="作答反馈">
              <p>你的答案：{selectedLabel ?? feedback.selected_option}</p>
              <p>结果：{resultLabel(feedback.result)}</p>
              <p><CitedText text={feedback.explanation} citations={feedback.citations} onCitation={(citation) => {
                const match = feedback.citations.find((item) => item.display_number === citation.display_number)
                if (match) setSelectedCitation(match)
              }} /></p>
              {feedback.citations.length > 0 && (
                <div className="citation-strip">
                  <span>来源</span>
                  {feedback.citations.map((citation) => (
                    <button className="citation-chip" type="button" key={citation.citation_id} onClick={() => setSelectedCitation(citation)}>
                      [{citation.display_number}] {citation.file_name}
                    </button>
                  ))}
                </div>
              )}
              {selectedCitation && feedback.citations.some((citation) => citation.citation_id === selectedCitation.citation_id) ? (
                <SourceCitationPanel citation={selectedCitation} onClose={() => setSelectedCitation(null)} />
              ) : null}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
