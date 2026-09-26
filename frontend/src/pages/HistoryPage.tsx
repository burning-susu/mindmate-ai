import { useRef, useState } from 'react'
import { History, LoaderCircle, MessageSquare } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { listConversationHistory, type ConversationHistoryItem } from '../api/history'
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

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

export default function HistoryPage() {
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
    <section className="history-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">对话历史</span>
          <h1>找回已保存的对话</h1>
          <p>这里只读取本机已保存的会话。打开记录不会重新生成回答。</p>
        </div>
        <Link className="quiet-button" to="/chat">返回对话</Link>
      </header>

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
    </section>
  )
}
