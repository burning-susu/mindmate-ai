import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, WifiOff } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { v7 as uuidv7 } from 'uuid'

import { ApiError, apiRequest } from '../api/client'
import {
  createNextLearningQuestion,
  finishLearningSession,
  getLearningSession,
  getLearningProviderPlan,
  submitLearningAttempt,
  type LearningCitation,
  type LearningFeedback,
  type LearningQuestion,
  type LearningSession,
} from '../api/learning'
import { type KnowledgeBaseItem } from '../api/knowledgeBases'
import { CitedText, SourceCitationPanel } from '../components/SourceCitationPanel'
import { useNetworkStatus } from '../useNetworkStatus'

const MOCK_BANNER = '新建学习会话使用当前选择。Mock 仍按本地规则出题和评分，不会外发。在线模式每道题和每次点评前都会单独确认费用。已经创建的会话保持创建时的服务。这仍不是完整学习计划或复习。'

function resultLabel(result: string) {
  if (result === 'CORRECT') return '正确'
  if (result === 'INCORRECT') return '不正确'
  return result
}

function canRevise(session: LearningSession) {
  const code = session.status === 'SOURCE_INVALID' ? 'SOURCE_INVALID' : session.failure_code
  return code === 'EVIDENCE_INSUFFICIENT'
    || code === 'CANNOT_FORM_RELIABLE_QUESTION'
    || code === 'MODEL_OUTPUT_REJECTED'
    || code === 'LEARNING_PROVIDER_INTERRUPTED'
}

function explanationLabel(origin: string | null | undefined) {
  if (origin === 'model_verified') return '在线模型生成的解释'
  if (origin === 'local_rule' || !origin) return '本地规则评分'
  return '点评待完成或不可用'
}

function blocksAnswer(session: LearningSession) {
  return session.status === 'FAILED' || session.status === 'SOURCE_INVALID' || Boolean(session.failure_code && !session.question)
}

function readFailureMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return '学习会话暂时读不到。服务恢复后点“重新读取”，会回到同一题和已保存的反馈。'
}

function endReasonLabel(reason: string | null | undefined) {
  if (reason === 'PLAN_COMPLETED') return '已完成计划题数'
  if (reason === 'USER_ENDED') return '主动结束'
  if (reason === 'EVIDENCE_EXHAUSTED') return '资料不足，已提前结束'
  if (reason === 'PROVIDER_RESULT_UNKNOWN') return '外发结果未知，已停止重发'
  if (reason === 'QUESTION_GENERATION_FAILED') return '下一题生成失败'
  return '学习已结束'
}

function answerLabel(question: LearningQuestion, feedback: LearningFeedback) {
  return question.options.find((option) => option.option_id === feedback.selected_option)?.label
    ?? feedback.selected_option
}

export default function LearningSessionPage() {
  const { sessionId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const focusQuestionId = searchParams.get('question') ?? ''
  const focusFeedback = searchParams.get('focus') === 'feedback'
  const queryClient = useQueryClient()
  const sessionQuery = useQuery({
    queryKey: ['learning-session', sessionId],
    queryFn: () => getLearningSession(sessionId),
    enabled: Boolean(sessionId),
    staleTime: 0,
    refetchOnMount: 'always',
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return false
      if (data.status === 'PREPARING') return 1500
      if (data.question_operation_status === 'DISPATCHED' || data.feedback_operation_status === 'DISPATCHED') return 1500
      return false
    },
  })
  const session = sessionQuery.data
  const sessionQuestions = session?.questions ?? (session?.question ? [session.question] : [])
  const knowledgeBaseQuery = useQuery({
    queryKey: ['knowledge-base', session?.knowledge_base_id],
    queryFn: () => apiRequest<KnowledgeBaseItem>(`/api/v1/knowledge-bases/${session?.knowledge_base_id}`),
    enabled: Boolean(session?.knowledge_base_id),
  })
  const [selectedOption, setSelectedOption] = useState('')
  const [chargeConfirmed, setChargeConfirmed] = useState(false)
  const [nextChargeConfirmed, setNextChargeConfirmed] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [generatingNext, setGeneratingNext] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [nextError, setNextError] = useState('')
  const [finishError, setFinishError] = useState('')
  const [pendingFeedback, setPendingFeedback] = useState<LearningFeedback | null>(null)
  const [selectedCitation, setSelectedCitation] = useState<LearningCitation | null>(null)
  const clientRequestId = useRef<string | null>(null)
  const nextRequestId = useRef<string | null>(null)
  const nextSourceQuestionId = useRef<string | null>(null)
  const finishRequestId = useRef<string | null>(null)
  const submitLock = useRef(false)
  const nextLock = useRef(false)
  const finishLock = useRef(false)
  const observedQuestionId = useRef<string | null>(null)
  const question = session?.question ?? null
  const sessionStatus = session?.status
  const sessionQuestionId = session?.current_question_id
  const questionMissing = Boolean(
    focusQuestionId && session && !sessionQuestions.some((item) => item.question_id === focusQuestionId),
  )
  const feedbackMissing = Boolean(
    focusFeedback
    && focusQuestionId
    && session
    && !sessionQuestions.find((item) => item.question_id === focusQuestionId)?.feedback
    && !pendingFeedback,
  )
  useEffect(() => {
    const currentQuestionId = session?.current_question_id ?? null
    if (!currentQuestionId || currentQuestionId === observedQuestionId.current) return
    observedQuestionId.current = currentQuestionId
    setSelectedOption('')
    setChargeConfirmed(false)
    setPendingFeedback(null)
    setSubmitError('')
    clientRequestId.current = null
    submitLock.current = false
  }, [session?.current_question_id])
  useEffect(() => {
    if (!nextRequestId.current || !sessionStatus) return
    if (
      sessionStatus === 'COMPLETED'
      || sessionStatus === 'FAILED'
      || sessionStatus === 'SOURCE_INVALID'
      || (sessionStatus !== 'PREPARING' && sessionQuestionId !== nextSourceQuestionId.current)
    ) {
      nextRequestId.current = null
      nextSourceQuestionId.current = null
      setNextChargeConfirmed(false)
    }
  }, [sessionQuestionId, sessionStatus])
  useEffect(() => {
    if (!focusQuestionId) return
    const targetId = focusFeedback
      ? `learning-feedback-${focusQuestionId}`
      : `learning-question-${focusQuestionId}`
    const node = document.getElementById(targetId)
    node?.scrollIntoView({ block: 'center' })
    node?.classList.add('history-target')
  }, [focusFeedback, focusQuestionId, question])
  const feedback = question?.feedback ?? pendingFeedback
  const answered = Boolean(feedback)
  const blocked = session
    ? (session.status !== 'IN_PROGRESS' && !(session.status === 'PREPARING' && answered))
      || (blocksAnswer(session) && !answered)
    : false
  const onlineSession = Boolean(session && session.provider !== 'mock')
  const networkOnline = useNetworkStatus()
  const offlineProviderBlocked = onlineSession && !networkOnline
  const canContinue = Boolean(
    session
    && answered
    && session.status === 'IN_PROGRESS'
    && session.completed_question_count < session.target_question_count,
  )
  const providerPlanQuery = useQuery({
    queryKey: ['learning-provider-plan'],
    queryFn: getLearningProviderPlan,
    enabled: onlineSession && canContinue,
    retry: false,
  })

  const refreshSession = async () => {
    const latest = await getLearningSession(sessionId)
    queryClient.setQueryData(['learning-session', sessionId], latest)
    return latest
  }

  const createNext = async () => {
    if (!session || !canContinue || nextLock.current) return
    if (offlineProviderBlocked || (onlineSession && (
      !nextChargeConfirmed
      || !providerPlanQuery.data
      || providerPlanQuery.data.budget_blocks
    ))) return
    nextLock.current = true
    setGeneratingNext(true)
    setNextError('')
    if (!nextRequestId.current) nextRequestId.current = uuidv7()
    if (!nextSourceQuestionId.current) nextSourceQuestionId.current = session.current_question_id
    try {
      const latest = await createNextLearningQuestion(
        sessionId,
        {
          expectedSessionVersion: session.row_version,
          confirmProviderCharge: onlineSession && nextChargeConfirmed,
        },
        nextRequestId.current,
      )
      queryClient.setQueryData(['learning-session', sessionId], latest)
      nextRequestId.current = null
      setNextChargeConfirmed(false)
      setNextError('')
    } catch (caught) {
      try {
        const latest = await refreshSession()
        if (latest.status === 'PREPARING') {
          setNextError('下一题正在处理。刷新后仍会回到同一请求，不会自动重发。')
        } else if (latest.current_question_id !== session.current_question_id || latest.result) {
          nextRequestId.current = null
          setNextChargeConfirmed(false)
        } else if (caught instanceof ApiError) {
          setNextError(caught.problem.detail)
        } else {
          setNextError('生成结果未知。请重新读取会话，不要更换这次请求。')
        }
      } catch {
        setNextError('生成结果未知，暂时读不到服务端状态。请稍后重新读取，不要更换这次请求。')
      }
    } finally {
      nextLock.current = false
      setGeneratingNext(false)
    }
  }

  const finish = async () => {
    if (!session || finishing || finishLock.current) return
    finishLock.current = true
    setFinishing(true)
    setFinishError('')
    if (!finishRequestId.current) finishRequestId.current = uuidv7()
    try {
      const latest = await finishLearningSession(
        sessionId,
        session.row_version,
        finishRequestId.current,
      )
      queryClient.setQueryData(['learning-session', sessionId], latest)
      setFinishError('')
    } catch (caught) {
      try {
        const latest = await refreshSession()
        if (latest.status === 'COMPLETED') setFinishError('')
        else if (caught instanceof ApiError) setFinishError(caught.problem.detail)
        else setFinishError('结束结果未知。请重新读取会话。')
      } catch {
        setFinishError('结束结果未知，暂时读不到服务端状态。请重新读取会话。')
      }
    } finally {
      finishLock.current = false
      setFinishing(false)
    }
  }

  const submit = async () => {
    if (!question || !selectedOption || answered || blocked || submitLock.current) return
    if (offlineProviderBlocked || (onlineSession && !chargeConfirmed)) return
    submitLock.current = true
    setSubmitting(true)
    setSubmitError('')
    if (!clientRequestId.current) clientRequestId.current = uuidv7()
    const requestId = clientRequestId.current
    try {
      const result = await submitLearningAttempt(
        question.question_id,
        {
          selectedOption,
          expectedQuestionVersion: question.row_version,
          confirmProviderCharge: onlineSession && chargeConfirmed,
        },
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
    const notFound = sessionQuery.error instanceof ApiError && sessionQuery.error.status === 404
    return (
      <section className="detail-page learning-page">
        <p className="learning-mock-banner" role="status">{MOCK_BANNER}</p>
        <div className="inline-error" role="alert">
          <span>{notFound ? '这个学习会话不存在或已进入回收站，未提交新的答案。' : readFailureMessage(sessionQuery.error)}</span>
          {notFound ? null : <button className="quiet-button" type="button" onClick={() => void sessionQuery.refetch()}>重新读取</button>}
          <Link className="quiet-button" to="/knowledge-bases">返回知识库</Link>
        </div>
      </section>
    )
  }

  const selectedLabel = question?.options.find((option) => option.option_id === (feedback?.selected_option ?? selectedOption))?.label
  const knowledgeBaseName = knowledgeBaseQuery.data?.name ?? session.knowledge_base_id
  const activeQuestionId = session.current_question_id ?? question?.question_id
  const questionHistory = sessionQuestions.filter((item) => {
    if (session.status === 'IN_PROGRESS' || session.status === 'PREPARING') {
      return item.feedback && item.question_id !== activeQuestionId
    }
    return item.feedback || item.status !== 'ANSWERED'
  })

  return (
    <section className="detail-page learning-page">
      <div className="detail-heading__actions">
        <Link className="back-link" to={`/knowledge-bases/${session.knowledge_base_id}`}>
          <ArrowLeft size={16} aria-hidden="true" />返回知识库
        </Link>
        <Link className="quiet-button" to="/history?tab=learning">学习历史</Link>
      </div>
      <p className="learning-mock-banner" role="status">{MOCK_BANNER}</p>
      <div className="detail-heading">
        <div>
          <span className="eyebrow">学习会话</span>
          <h1>{session.topic}</h1>
          <p>目标：{session.goal_text}</p>
          <p>资料范围：{knowledgeBaseName} · {session.scope?.file_ids.length ?? 0} 个文件 · 题量 {session.target_question_count}</p>
          <p>已完成 {session.completed_question_count} / {session.target_question_count} 题</p>
          {session.plan?.knowledge_point_title && <p id="learning-knowledge-point">知识点：{session.plan.knowledge_point_title}</p>}
          <p>模型 {session.model} · live_model_called={String(session.live_model_called)}</p>
          <p>
            服务 {session.provider}
            {session.requested_model ? ` · 请求模型 ${session.requested_model}` : ''}
            {session.resolved_model ? ` · 返回模型 ${session.resolved_model}` : ''}
            {session.question_operation_status ? ` · 出题 ${session.question_operation_status}` : ''}
            {session.feedback_operation_status ? ` · 点评 ${session.feedback_operation_status}` : ''}
            {session.live_model_called ? ' · 已外发' : ' · 未外发'}
          </p>
          {session.status === 'PREPARING' || session.question_operation_status === 'DISPATCHED' ? (
            <p role="status">正在等待所选服务返回题目。刷新后会回到同一次请求，不会自动再发。</p>
          ) : null}
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
      {questionMissing ? (
        <div className="inline-error" role="alert">这道题不在当前画面。不会提交答案，也不会新开学习会话。</div>
      ) : null}
      {feedbackMissing ? (
        <div className="inline-error" role="alert">这份反馈还没有发布。不会为了定位而提交答案。</div>
      ) : null}
      {question && !blocked && (
        <div className="detail-section learning-question" id={`learning-question-${question.question_id}`} tabIndex={-1}>
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
          {offlineProviderBlocked ? <p className="chat-alert chat-alert--warning" role="alert"><WifiOff size={15} aria-hidden="true" /> 当前设备处于离线状态，不会向在线 Provider 发送点评请求。恢复网络后请显式重试。</p> : null}
          {!answered && onlineSession && (
            <label>
              <input
                type="checkbox"
                checked={chargeConfirmed}
                onChange={(event) => setChargeConfirmed(event.target.checked)}
              />
              我确认把当前答案和必要依据发给 {session.provider} 请求点评，并接受本次费用估算
            </label>
          )}
          {!answered && (
            <button className="primary-button" type="button" disabled={!selectedOption || submitting || offlineProviderBlocked || (onlineSession && !chargeConfirmed)} aria-busy={submitting} onClick={() => void submit()}>
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
            <div className="learning-feedback" id={`learning-feedback-${question.question_id}`} aria-label="作答反馈" tabIndex={-1}>
              <p>你的答案：{selectedLabel ?? feedback.selected_option}</p>
              <p>结果：{resultLabel(feedback.result)}</p>
              <p>{explanationLabel(feedback.explanation_origin)}{feedback.live_model_called ? ' · 点评已外发' : ''}</p>
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
            </div>
          )}
        </div>
      )}
      {session.status === 'PREPARING' && sessionQuestions.length > 0 && (
        <p role="status">正在准备下一题。刷新后会读取同一会话状态。</p>
      )}
      {canContinue && (
        <section className="detail-section learning-next-question" aria-label="下一题">
          {onlineSession && providerPlanQuery.data && (
            <div className="settings-privacy-copy">
              {providerPlanQuery.data.budget_notice ? <p role="alert">{providerPlanQuery.data.budget_notice}</p> : null}
              <p>{providerPlanQuery.data.outbound_summary}</p>
              <p>
                本次下一题将发送给 {providerPlanQuery.data.provider}，按公开费率估算不超过
                {' '}{providerPlanQuery.data.question_estimate.estimated_usd_ceiling} 美元。
                {providerPlanQuery.data.question_estimate.disclaimer}
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={nextChargeConfirmed}
                  onChange={(event) => setNextChargeConfirmed(event.target.checked)}
                />
                我确认本次生成下一题可能产生费用
              </label>
            </div>
          )}
          {onlineSession && providerPlanQuery.isLoading && <p role="status">正在读取本次费用估算…</p>}
          {onlineSession && providerPlanQuery.isError && (
            <div className="inline-error" role="alert">费用估算暂时不可用，不能外发下一题。</div>
          )}
          {offlineProviderBlocked ? <p className="chat-alert chat-alert--warning" role="alert"><WifiOff size={15} aria-hidden="true" /> 当前设备处于离线状态，不会生成下一题。恢复网络后请显式重试。</p> : null}
          {nextError && (
            <div className="inline-error" role="alert">
              <span>{nextError}</span>
              <button className="quiet-button" type="button" onClick={() => void refreshSession().catch(() => setNextError('重新读取失败。'))}>重新读取</button>
            </div>
          )}
          <button
            className="primary-button"
            type="button"
            disabled={generatingNext || offlineProviderBlocked || (onlineSession && (
              !nextChargeConfirmed
              || !providerPlanQuery.data
              || providerPlanQuery.data.budget_blocks
            ))}
            aria-busy={generatingNext}
            onClick={() => void createNext()}
          >
            {generatingNext ? '正在生成' : '下一题'}
          </button>
        </section>
      )}
      {questionHistory.length > 0 && (
        <section className="detail-section learning-question-history" aria-label="已完成题目">
          <h2>题目记录</h2>
          {questionHistory.map((item) => {
              const itemFeedback = item.feedback
              return (
                <article className="learning-feedback" id={`learning-question-${item.question_id}`} key={item.question_id}>
                  <h3>第 {item.sequence_number} 题</h3>
                  <p>{item.prompt_text}</p>
                  {itemFeedback ? (
                    <div id={`learning-feedback-${item.question_id}`} aria-label="作答反馈">
                      <p>你的答案：{answerLabel(item, itemFeedback)}</p>
                      <p>结果：{resultLabel(itemFeedback.result)}</p>
                      <p>{explanationLabel(itemFeedback.explanation_origin)}{itemFeedback.live_model_called ? ' · 点评已外发' : ''}</p>
                      <p><CitedText text={itemFeedback.explanation} citations={itemFeedback.citations} onCitation={(citation) => {
                        const match = itemFeedback.citations.find((citationItem) => citationItem.display_number === citation.display_number)
                        if (match) setSelectedCitation(match)
                      }} /></p>
                      {itemFeedback.citations.length > 0 && (
                        <div className="citation-strip">
                          <span>来源</span>
                          {itemFeedback.citations.map((citation) => (
                            <button className="citation-chip" type="button" key={citation.citation_id} onClick={() => setSelectedCitation(citation)}>
                              [{citation.display_number}] {citation.file_name}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : <p>未提交作答</p>}
                </article>
              )
            })}
        </section>
      )}
      {session.result && (
        <section className="detail-section learning-session-result" aria-label="本次学习结果">
          <h2>本次学习结果</h2>
          <p>实际完成 {session.result.completed_question_count} / {session.result.planned_question_count} 题</p>
          <p>正确 {session.result.correct_count} · 错误 {session.result.incorrect_count} · 无法判定 {session.result.unjudged_count}</p>
          <p>{endReasonLabel(session.result.end_reason)}</p>
        </section>
      )}
      {session.status !== 'COMPLETED' && session.status !== 'PREPARING' && (
        <div className="detail-heading__actions">
          {finishError && <span className="inline-error" role="alert">{finishError}</span>}
          <button className="quiet-button" type="button" disabled={finishing} onClick={() => void finish()}>
            {finishing ? '正在结束' : '结束学习'}
          </button>
        </div>
      )}
      {selectedCitation && (
        <SourceCitationPanel citation={selectedCitation} onClose={() => setSelectedCitation(null)} />
      )}
    </section>
  )
}
