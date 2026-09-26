import { useRef, useState } from 'react'
import { GraduationCap, History, LoaderCircle, MessageSquare } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import {
  listConversationHistory,
  listLearningHistory,
  type ConversationHistoryItem,
  type LearningHistoryItem,
} from '../api/history'
import { sourceStatusLabel } from '../components/sourceStatus'

function modeLabel(mode: string): string {
  return mode === 'KNOWLEDGE_CHAT' ? '知识库' : '普通聊天'
}

function statusLabel(status: string): string {
  return {
    ACTIVE: '可阅读',
    INTERRUPTED: '上次生成已中断',
    SOURCE_INVALID: '资料范围已失效',
  }[status] ?? status
}

function learningStatusLabel(status: string, answeredCount: number): string {
  if (status === 'SOURCE_INVALID') return '资料范围已失效'
  if (status === 'FAILED') return '未能出题'
  if (answeredCount > 0) return '已作答'
  if (status === 'IN_PROGRESS') return '未作答'
  return status
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function ConversationHistory() {
  const navigate = useNavigate()
  const [cursor, setCursor] = useState<string | undefined>()
  const [items, setItems] = useState<ConversationHistoryItem[]>([])
  const openingRef = useRef('')
  const [openingId, setOpeningId] = useState('')
  const historyQuery = useQuery({
    queryKey: ['conversation-history', cursor ?? ''],
    queryFn: () => listConversationHistory(cursor),
    retry: false,
  })
  const pageItems = historyQuery.data?.items
  const visibleItems = cursor ? items.concat(pageItems ?? []) : (pageItems ?? items)

  const openConversation = (conversationId: string) => {
    if (openingRef.current === conversationId) return
    openingRef.current = conversationId
    setOpeningId(conversationId)
    navigate(`/chat/${conversationId}`)
  }

  const showMore = () => {
    const next = historyQuery.data?.next_cursor
    if (!next || historyQuery.isFetching) return
    setItems(visibleItems)
    setCursor(next)
  }

  return (
    <div className="history-panel">
      <p>打开已保存的对话不会重新生成回答。</p>
      {historyQuery.isLoading ? (
        <div className="history-state" role="status"><LoaderCircle className="spin" size={16} /> 正在加载对话历史</div>
      ) : null}
      {historyQuery.isError ? (
        <div className="history-state history-state--error" role="alert">
          <span>对话历史暂时读不出来。</span>
          <button className="quiet-button" type="button" onClick={() => void historyQuery.refetch()}>重新加载</button>
        </div>
      ) : null}
      {!historyQuery.isLoading && !historyQuery.isError && visibleItems.length === 0 ? (
        <div className="history-state">还没有可阅读的对话。发送过的对话会保留在这里。</div>
      ) : null}
      <div className="history-list">
        {visibleItems.map((item) => (
          <button
            className="history-item"
            key={item.conversation_id}
            type="button"
            disabled={openingId === item.conversation_id}
            onClick={() => openConversation(item.conversation_id)}
          >
            <MessageSquare size={16} aria-hidden="true" />
            <span>
              <strong>{item.title || item.summary || '未命名对话'}</strong>
              <small>{item.summary}</small>
              <small>会话 {item.conversation_id}</small>
            </span>
            <span className="history-item__meta">
              <em>{modeLabel(item.current_mode)}{item.scope_name ? ` · ${item.scope_name}` : ''}</em>
              <em>{statusLabel(item.status)} · {sourceStatusLabel(item.source_status)}</em>
              <em>{formatTime(item.updated_at)} · {item.message_count} 条消息</em>
            </span>
            {openingId === item.conversation_id ? <span>正在打开</span> : <History size={14} aria-hidden="true" />}
          </button>
        ))}
      </div>
      {historyQuery.data?.next_cursor ? (
        <button className="quiet-button" type="button" onClick={showMore} disabled={historyQuery.isFetching}>
          {historyQuery.isFetching ? '正在加载更多' : '加载更多'}
        </button>
      ) : null}
    </div>
  )
}

function LearningHistory() {
  const navigate = useNavigate()
  const [cursor, setCursor] = useState<string | undefined>()
  const [items, setItems] = useState<LearningHistoryItem[]>([])
  const openingRef = useRef('')
  const [openingId, setOpeningId] = useState('')
  const historyQuery = useQuery({
    queryKey: ['learning-history', cursor ?? ''],
    queryFn: () => listLearningHistory(cursor),
    retry: false,
  })
  const pageItems = historyQuery.data?.items
  const visibleItems = cursor ? items.concat(pageItems ?? []) : (pageItems ?? items)

  const openSession = (learningSessionId: string) => {
    if (openingRef.current === learningSessionId) return
    openingRef.current = learningSessionId
    setOpeningId(learningSessionId)
    navigate(`/learning/session/${learningSessionId}`)
  }

  const showMore = () => {
    const next = historyQuery.data?.next_cursor
    if (!next || historyQuery.isFetching) return
    setItems(visibleItems)
    setCursor(next)
  }

  return (
    <div className="history-panel">
      <p>打开已保存的学习会话不会重新出题，也不会自动提交答案。</p>
      {historyQuery.isLoading ? (
        <div className="history-state" role="status"><LoaderCircle className="spin" size={16} /> 正在加载学习历史</div>
      ) : null}
      {historyQuery.isError ? (
        <div className="history-state history-state--error" role="alert">
          <span>学习历史暂时读不出来。</span>
          <button className="quiet-button" type="button" onClick={() => void historyQuery.refetch()}>重新加载</button>
        </div>
      ) : null}
      {!historyQuery.isLoading && !historyQuery.isError && visibleItems.length === 0 ? (
        <div className="history-state">还没有可找回的学习会话。从知识库开始的一题会保留在这里。</div>
      ) : null}
      <div className="history-list">
        {visibleItems.map((item) => (
          <button
            className="history-item"
            key={item.learning_session_id}
            type="button"
            disabled={openingId === item.learning_session_id}
            onClick={() => openSession(item.learning_session_id)}
          >
            <GraduationCap size={16} aria-hidden="true" />
            <span>
              <strong>{item.topic || '未命名学习'}</strong>
              <small>{item.scope_name ?? '资料范围不可用'} · {item.scope_file_count} 个文件</small>
              <small>会话 {item.learning_session_id}</small>
            </span>
            <span className="history-item__meta">
              <em>{learningStatusLabel(item.status, item.answered_count)} · {sourceStatusLabel(item.source_status)}</em>
              <em>已作答 {item.answered_count} / {item.target_question_count}</em>
              <em>{formatTime(item.updated_at)}</em>
            </span>
            {openingId === item.learning_session_id ? <span>正在打开</span> : <History size={14} aria-hidden="true" />}
          </button>
        ))}
      </div>
      {historyQuery.data?.next_cursor ? (
        <button className="quiet-button" type="button" onClick={showMore} disabled={historyQuery.isFetching}>
          {historyQuery.isFetching ? '正在加载更多' : '加载更多'}
        </button>
      ) : null}
    </div>
  )
}

export default function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const learningTab = searchParams.get('tab') === 'learning'

  const selectTab = (tab: 'conversations' | 'learning') => {
    const next = new URLSearchParams(searchParams)
    if (tab === 'learning') next.set('tab', 'learning')
    else next.delete('tab')
    setSearchParams(next, { replace: true })
  }

  return (
    <section className="history-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">历史记录</span>
          <h1>找回已保存的对话和学习</h1>
          <p>这里只读取本机已经保存的记录。打开它们不会重新生成回答或题目。</p>
        </div>
        <Link className="quiet-button" to={learningTab ? '/learning' : '/chat'}>
          {learningTab ? '返回学习' : '返回对话'}
        </Link>
      </header>
      <div className="history-tabs" role="tablist" aria-label="历史类型">
        <button className={`history-tab ${learningTab ? '' : 'history-tab--active'}`} type="button" role="tab" aria-selected={!learningTab} onClick={() => selectTab('conversations')}>对话历史</button>
        <button className={`history-tab ${learningTab ? 'history-tab--active' : ''}`} type="button" role="tab" aria-selected={learningTab} onClick={() => selectTab('learning')}>学习历史</button>
      </div>
      {learningTab ? <LearningHistory /> : <ConversationHistory />}
    </section>
  )
}
