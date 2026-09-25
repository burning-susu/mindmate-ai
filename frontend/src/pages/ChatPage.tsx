/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useMemo, useRef, useState } from 'react'
import { LoaderCircle, MessageSquare, Plus, RefreshCw, Send, Square, WifiOff } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import {
  type ChatEvent,
  type Conversation,
  type Message,
  type Operation,
  createConversation,
  createMessage,
  getOperation,
  listConversations,
  listMessages,
  stopOperation,
  streamOperation,
} from '../api/chat'
import { ApiError } from '../api/client'

const ACTIVE_STATES = new Set(['QUEUED', 'RUNNING', 'STOPPING'])
const TERMINAL_STATES = new Set(['COMPLETED', 'FAILED', 'STOPPED', 'INTERRUPTED'])

function statusLabel(status: string): string {
  return {
    QUEUED: '准备中',
    RUNNING: '正在生成',
    STOPPING: '正在停止',
    COMPLETED: '已完成',
    STOPPED: '已停止',
    FAILED: '生成失败',
    INTERRUPTED: '已中断',
    SENT: '已发送',
    STREAMING: '正在生成',
    PENDING: '准备中',
  }[status] ?? status
}

function isTerminal(status: string): boolean {
  return TERMINAL_STATES.has(status)
}

function mergeMessage(messages: Message[], next: Message): Message[] {
  const index = messages.findIndex((message) => message.message_id === next.message_id)
  if (index < 0) return [...messages, next].sort((a, b) => a.sequence_number - b.sequence_number)
  const copy = [...messages]
  copy[index] = next
  return copy
}

function AssistantBody({ content }: { content: string }) {
  if (!content) return <span className="chat-message__placeholder">回答将在这里显示</span>
  return (
    <div className="chat-markdown" aria-label="AI 回答">
      {content.split(/\n{2,}/).map((paragraph, index) => (
        <p key={`${index}-${paragraph.slice(0, 12)}`}>{paragraph}</p>
      ))}
    </div>
  )
}

export default function ChatPage() {
  const { conversationId: routeConversationId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const selectedConversationId = routeConversationId ?? ''
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [operation, setOperation] = useState<Operation | null>(null)
  const [connectionState, setConnectionState] = useState<'idle' | 'connecting' | 'connected' | 'disconnected' | 'stopping'>('idle')
  const [sendError, setSendError] = useState('')
  const [retryCount, setRetryCount] = useState(0)
  const [streamNonce, setStreamNonce] = useState(0)
  const operationRef = useRef<Operation | null>(null)

  const conversationsQuery = useQuery({
    queryKey: ['chat-conversations'],
    queryFn: listConversations,
    staleTime: 5_000,
  })
  const conversationItems = conversationsQuery.data?.items
  const conversations = useMemo(() => conversationItems ?? [], [conversationItems])
  const selectedConversation = useMemo<Conversation | undefined>(
    () => conversations.find((item) => item.conversation_id === selectedConversationId),
    [conversations, selectedConversationId],
  )
  const messagesQuery = useQuery({
    queryKey: ['chat-messages', selectedConversationId],
    queryFn: () => listMessages(selectedConversationId),
    enabled: Boolean(selectedConversationId),
    staleTime: 1_000,
  })

  useEffect(() => {
    if (!selectedConversationId) {
      setMessages([])
      setOperation(null)
      return
    }
    if (messagesQuery.data?.items) setMessages(messagesQuery.data.items)
    const activeOperationId = selectedConversation?.active_operation_id
    if (!activeOperationId) {
      if (!operationRef.current || operationRef.current.conversation_id !== selectedConversationId) setOperation(null)
      return
    }
    void getOperation(activeOperationId)
      .then((next) => {
        operationRef.current = next
        setOperation(next)
        if (next.assistant_message) setMessages((current) => mergeMessage(current, next.assistant_message as Message))
      })
      .catch(() => undefined)
  }, [messagesQuery.data, selectedConversation, selectedConversationId])

  useEffect(() => {
    const currentOperation = operation
    if (!currentOperation) return
    operationRef.current = currentOperation
    const controller = new AbortController()
    let cancelled = false
    let cursor = currentOperation.event_sequence ?? currentOperation.stream_sequence ?? 0
    let attempts = 0

    const applyEvent = (event: ChatEvent) => {
      cursor = Math.max(cursor, event.id)
      const content = typeof event.data.content === 'string' ? event.data.content : undefined
      const status = typeof event.data.status === 'string' ? event.data.status : undefined
      if (content !== undefined && currentOperation.assistant_message_id) {
        setMessages((current) => {
          const existing = current.find((item) => item.message_id === currentOperation.assistant_message_id)
          if (!existing) return current
          return mergeMessage(current, {
            ...existing,
            content,
            status: status === 'COMPLETED' ? 'COMPLETED' : status === 'STOPPED' ? 'STOPPED' : status === 'FAILED' ? 'FAILED' : 'STREAMING',
            updated_at: new Date().toISOString(),
          })
        })
      }
      if (status === 'STOPPING') setConnectionState('stopping')
      else if (status === 'RUNNING') setConnectionState('connected')
      else if (status && isTerminal(status)) setConnectionState('idle')
    }

    const connect = async () => {
      while (!cancelled && attempts <= 3) {
        setConnectionState(attempts === 0 ? 'connecting' : 'disconnected')
        try {
          await streamOperation(currentOperation.operation_id, applyEvent, controller.signal, cursor)
          const latest = await getOperation(currentOperation.operation_id)
          if (cancelled) return
          operationRef.current = latest
          setOperation(latest)
          if (latest.assistant_message) setMessages((current) => mergeMessage(current, latest.assistant_message as Message))
          if (isTerminal(latest.status)) {
            setConnectionState('idle')
            void queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })
            void queryClient.invalidateQueries({ queryKey: ['chat-messages', latest.conversation_id] })
            return
          }
          attempts += 1
          setRetryCount(attempts)
          await new Promise((resolve) => window.setTimeout(resolve, 250 * attempts))
        } catch (error) {
          if (cancelled || (error instanceof DOMException && error.name === 'AbortError')) return
          attempts += 1
          setRetryCount(attempts)
          setConnectionState('disconnected')
          if (attempts > 3) return
          await new Promise((resolve) => window.setTimeout(resolve, 250 * attempts))
        }
      }
    }
    void connect()
    return () => {
      cancelled = true
      controller.abort()
    }
  // The stream lifecycle is keyed by operation id; status updates must not create a second reader.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operation?.operation_id, queryClient, streamNonce])

  const hasActiveOperation = Boolean(operation && ACTIVE_STATES.has(operation.status))

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const content = draft.trim()
    if (!content || hasActiveOperation) return
    setSendError('')
    setDraft('')
    try {
      const result = selectedConversationId && selectedConversation
        ? await createMessage(selectedConversationId, content, selectedConversation.row_version)
        : await createConversation(content)
      operationRef.current = result.operation
      setOperation(result.operation)
      setMessages((current) => {
        let next = current
        next = mergeMessage(next, result.user_message)
        next = mergeMessage(next, result.assistant_message)
        return next
      })
      navigate(`/chat/${result.conversation_id}`, { replace: true })
      void queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })
    } catch (error) {
      setDraft(content)
      setSendError(error instanceof ApiError ? error.problem.detail : '消息发送失败，请稍后重试。')
    }
  }

  const stop = async () => {
    if (!operation || !hasActiveOperation) return
    setConnectionState('stopping')
    try {
      let latest = await stopOperation(operation.operation_id)
      setOperation(latest)
      for (let attempt = 0; attempt < 20 && !isTerminal(latest.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 100))
        latest = await getOperation(operation.operation_id)
        setOperation(latest)
      }
      if (latest.assistant_message) setMessages((current) => mergeMessage(current, latest.assistant_message as Message))
      setConnectionState('idle')
    } catch (error) {
      setSendError(error instanceof ApiError ? error.problem.detail : '停止请求失败，请稍后重试。')
      setConnectionState('disconnected')
    }
  }

  const retryStream = () => {
    if (!operation) return
    setRetryCount(0)
    setStreamNonce((value) => value + 1)
  }

  return (
    <section className="chat-page">
      <header className="page-heading chat-page__heading">
        <div>
          <span className="eyebrow">AI 对话</span>
          <h1>普通聊天</h1>
          <p>当前为 GENERAL_CHAT，回答不使用知识库资料。</p>
        </div>
        <button className="primary-button" type="button" onClick={() => { setOperation(null); setMessages([]); navigate('/chat') }}>
          <Plus size={16} aria-hidden="true" /> 新建对话
        </button>
      </header>

      <div className="chat-layout">
        <aside className="chat-conversations" aria-label="会话列表">
          <div className="chat-panel-heading"><strong>最近对话</strong><span>{conversations.length}</span></div>
          {conversationsQuery.isLoading ? <div className="chat-list-state"><LoaderCircle className="spin" size={16} /> 正在加载</div> : null}
          {!conversationsQuery.isLoading && conversations.length === 0 ? <div className="chat-list-state">发送第一条消息后，会话会出现在这里。</div> : null}
          {conversations.map((conversation) => (
            <button
              className={`chat-conversation ${conversation.conversation_id === selectedConversationId ? 'chat-conversation--active' : ''}`}
              key={conversation.conversation_id}
              type="button"
              onClick={() => { setOperation(null); navigate(`/chat/${conversation.conversation_id}`) }}
            >
              <MessageSquare size={15} aria-hidden="true" />
              <span><strong>{conversation.title || '未命名对话'}</strong><small>{conversation.message_count} 条消息</small></span>
              {conversation.active_operation_id ? <LoaderCircle className="spin" size={14} aria-label="正在生成" /> : null}
            </button>
          ))}
        </aside>

        <div className="chat-main">
          <div className="chat-mode-bar">
            <span className="chat-mode-badge"><MessageSquare size={14} aria-hidden="true" /> 普通聊天</span>
            {operation ? <span className={`chat-operation-status chat-operation-status--${operation.status.toLowerCase()}`}>{statusLabel(operation.status)}</span> : null}
          </div>

          <div className="chat-messages" aria-live="polite">
            {!selectedConversationId ? (
              <div className="chat-empty"><MessageSquare size={28} /><strong>开始一段普通聊天</strong><span>输入问题后，回答会在此处逐步显示。</span></div>
            ) : messages.length === 0 && messagesQuery.isLoading ? (
              <div className="chat-empty"><LoaderCircle className="spin" size={24} /><span>正在加载消息</span></div>
            ) : messages.length === 0 ? (
              <div className="chat-empty"><span>这个会话还没有消息。</span></div>
            ) : messages.map((message) => (
              <article className={`chat-message chat-message--${message.role.toLowerCase()}`} key={message.message_id}>
                <div className="chat-message__meta"><strong>{message.role === 'USER' ? '你' : 'MindMate'}</strong>{message.role === 'ASSISTANT' && message.status !== 'COMPLETED' ? <span>{statusLabel(message.status)}</span> : null}</div>
                {message.role === 'ASSISTANT' ? <AssistantBody content={message.content} /> : <p className="chat-user-content">{message.content}</p>}
              </article>
            ))}
          </div>

          <div className="chat-compose-area">
            {connectionState === 'disconnected' ? <div className="chat-alert chat-alert--warning"><WifiOff size={15} /><span>连接暂时断开，后台任务仍会继续。</span><button className="quiet-button" type="button" onClick={retryStream}><RefreshCw size={14} /> 重连{retryCount ? `（${retryCount}/3）` : ''}</button></div> : null}
            {sendError ? <div className="chat-alert chat-alert--error">{sendError}</div> : null}
            <form className="chat-composer" onSubmit={submit}>
              <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="输入你的问题" aria-label="消息内容" rows={3} disabled={hasActiveOperation} />
              <div className="chat-composer__footer">
                {hasActiveOperation ? <button className="stop-button" type="button" onClick={stop}><Square size={15} fill="currentColor" /> {operation?.status === 'STOPPING' ? '正在停止' : '停止生成'}</button> : <button className="primary-button" type="submit" disabled={!draft.trim()}><Send size={15} /> 发送</button>}
              </div>
            </form>
          </div>
        </div>
      </div>
    </section>
  )
}
