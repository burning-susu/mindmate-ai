import { useEffect, useRef, useState, type ReactNode } from 'react'
import { GraduationCap, History, LoaderCircle, MessageSquare, X } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import {
  listConversationHistory,
  listHistoryTrash,
  listLearningHistory,
  purgeConversation,
  purgeLearningSession,
  restoreConversation,
  restoreLearningSession,
  trashConversation,
  trashLearningSession,
  type ConversationHistoryItem,
  type HistoryFilters,
  type HistoryTrashItem,
  type LearningHistoryItem,
} from '../api/history'
import { ApiError } from '../api/client'
import { sourceStatusLabel } from '../components/sourceStatus'
import { queryClient } from '../queryClient'

const CONVERSATION_MODES = [
  ['', '全部模式'],
  ['GENERAL_CHAT', '普通聊天'],
  ['KNOWLEDGE_CHAT', '知识库聊天'],
] as const

const CONVERSATION_STATUSES = [
  ['', '全部状态'],
  ['ACTIVE', '可继续'],
  ['SOURCE_INVALID', '来源失效'],
  ['INTERRUPTED', '异常中断'],
] as const

const LEARNING_STATUSES = [
  ['', '全部状态'],
  ['IN_PROGRESS', '进行中'],
  ['PREPARING', '准备中'],
  ['COMPLETED', '已完成'],
  ['FAILED', '未能出题'],
  ['SOURCE_INVALID', '来源失效'],
] as const

const CONVERSATION_SOURCES = [
  ['', '全部来源'],
  ['AVAILABLE', '来源可用'],
  ['NOT_APPLICABLE', '普通聊天'],
  ['SOURCE_IN_TRASH', '来源在回收站'],
  ['SOURCE_DELETED', '来源已删除'],
  ['INDEX_VERSION_RETIRED', '索引不可用'],
  ['PARTIAL_SOURCE', '部分来源失效'],
  ['SOURCE_OUT_OF_SCOPE', '来源超出范围'],
] as const

const LEARNING_SOURCES = [
  ['', '全部来源'],
  ['AVAILABLE', '来源可用'],
  ['SOURCE_IN_TRASH', '来源在回收站'],
  ['SOURCE_DELETED', '来源已删除'],
  ['SOURCE_VERSION_STALE', '来源内容已变化'],
  ['INDEX_VERSION_RETIRED', '索引不可用'],
  ['PARTIAL_SOURCE', '部分来源失效'],
  ['SOURCE_OUT_OF_SCOPE', '来源超出范围'],
] as const

function modeLabel(mode: string): string {
  return mode === 'KNOWLEDGE_CHAT' ? '知识库' : '普通聊天'
}

function statusLabel(status: string): string {
  return {
    ACTIVE: '可阅读',
    INTERRUPTED: '上次生成已中断',
    SOURCE_INVALID: '资料范围已失效',
    PREPARING: '准备中',
    FAILED: '未能出题',
  }[status] ?? status
}

function learningStatusLabel(status: string, answeredCount: number): string {
  if (status === 'SOURCE_INVALID') return '资料范围已失效'
  if (status === 'FAILED') return '未能出题'
  if (status === 'PREPARING') return '准备中'
  if (status === 'COMPLETED') return '已完成'
  if (answeredCount > 0) return '已作答'
  if (status === 'IN_PROGRESS') return '未作答'
  return status
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function labelOf(options: readonly (readonly [string, string])[], value: string): string {
  return options.find(([key]) => key === value)?.[1] ?? value
}

function readFilters(params: URLSearchParams, prefix: 'c' | 'l'): HistoryFilters {
  return {
    q: params.get(`${prefix}q`) ?? '',
    mode: params.get(`${prefix}mode`) ?? '',
    goalType: params.get(`${prefix}goal`) ?? '',
    status: params.get(`${prefix}status`) ?? '',
    sourceStatus: params.get(`${prefix}source`) ?? '',
    dateFrom: params.get(`${prefix}from`) ?? '',
    dateTo: params.get(`${prefix}to`) ?? '',
  }
}

function activeFilterText(filters: HistoryFilters, kind: 'conversation' | 'learning'): string {
  const parts = [
    filters.q ? `关键词“${filters.q}”` : '',
    kind === 'conversation' && filters.mode ? labelOf(CONVERSATION_MODES, filters.mode) : '',
    kind === 'learning' && filters.goalType ? '自定义目标' : '',
    filters.status
      ? labelOf(kind === 'conversation' ? CONVERSATION_STATUSES : LEARNING_STATUSES, filters.status)
      : '',
    filters.sourceStatus
      ? labelOf(kind === 'conversation' ? CONVERSATION_SOURCES : LEARNING_SOURCES, filters.sourceStatus)
      : '',
    filters.dateFrom || filters.dateTo ? `${filters.dateFrom || '不限'} 至 ${filters.dateTo || '不限'}` : '',
  ].filter(Boolean)
  return parts.join('，')
}

function hasFilters(filters: HistoryFilters): boolean {
  return Object.values(filters).some((value) => Boolean(value))
}

const SECTION_LABEL: Record<string, string> = {
  title: '标题',
  user_message: '你的问题',
  assistant_message: '已完成回答',
  summary: '摘要',
  topic: '主题',
  goal: '目标',
  question: '题干',
  submitted_answer: '已提交答案',
  feedback: '已发布反馈',
  knowledge_point: '知识点',
}

type HistoryHit = { section: string; snippet: string; record_id?: string | null }

function HighlightedSnippet({ text, keyword }: { text: string; keyword: string }) {
  const needle = keyword.trim()
  if (!needle) return <>{text}</>
  const folded = text.toLocaleLowerCase()
  const target = needle.toLocaleLowerCase()
  const parts: ReactNode[] = []
  let cursor = 0
  let found = folded.indexOf(target)
  while (found >= 0) {
    if (found > cursor) parts.push(text.slice(cursor, found))
    parts.push(<mark key={`${found}-${cursor}`}>{text.slice(found, found + target.length)}</mark>)
    cursor = found + target.length
    found = folded.indexOf(target, cursor)
  }
  if (cursor < text.length) parts.push(text.slice(cursor))
  return <>{parts}</>
}

function locationHref(kind: 'conversation' | 'learning', ownerId: string, location: HistoryHit): string {
  const recordId = location.record_id ?? ''
  if (kind === 'conversation') {
    if (recordId && (location.section === 'user_message' || location.section === 'assistant_message')) {
      return `/chat/${ownerId}?message=${encodeURIComponent(recordId)}`
    }
    return `/chat/${ownerId}`
  }
  if (location.section === 'feedback' && recordId) {
    return `/learning/session/${ownerId}?question=${encodeURIComponent(recordId)}&focus=feedback`
  }
  if ((location.section === 'question' || location.section === 'submitted_answer') && recordId) {
    return `/learning/session/${ownerId}?question=${encodeURIComponent(recordId)}`
  }
  if (location.section === 'knowledge_point') {
    return `/learning/session/${ownerId}#learning-knowledge-point`
  }
  if (location.section === 'summary') {
    return `/learning/session/${ownerId}?focus=summary`
  }
  return `/learning/session/${ownerId}`
}

function HistoryHits({
  kind,
  ownerId,
  keyword,
  locations,
}: {
  kind: 'conversation' | 'learning'
  ownerId: string
  keyword: string
  locations: HistoryHit[] | undefined
}) {
  if (!locations?.length) return null
  return (
    <span className="history-hits">
      {locations.map((location) => (
        <Link
          key={`${location.section}-${location.record_id ?? ''}-${location.snippet}`}
          to={locationHref(kind, ownerId, location)}
        >
          命中{SECTION_LABEL[location.section] ?? location.section}：
          <HighlightedSnippet text={location.snippet} keyword={keyword} />
        </Link>
      ))}
    </span>
  )
}

function usePagedItems<T>(filterKey: string) {
  const [pager, setPager] = useState({ filterKey, cursor: undefined as string | undefined, previous: [] as T[] })
  if (pager.filterKey !== filterKey) {
    setPager({ filterKey, cursor: undefined, previous: [] })
  }
  const current = pager.filterKey === filterKey ? pager : { filterKey, cursor: undefined, previous: [] as T[] }
  return {
    cursor: current.cursor,
    previous: current.previous,
    showMore(next: string, visible: T[]) {
      setPager({ filterKey, cursor: next, previous: visible })
    },
    reset() {
      setPager({ filterKey, cursor: undefined, previous: [] })
    },
  }
}

function FilterBar({
  kind,
  filters,
  draft,
  onDraft,
  onChange,
  onClear,
}: {
  kind: 'conversation' | 'learning'
  filters: HistoryFilters
  draft: string
  onDraft: (value: string) => void
  onChange: (patch: HistoryFilters) => void
  onClear: () => void
}) {
  const enabled = activeFilterText(filters, kind)
  return (
    <form className="history-filters" onSubmit={(event) => event.preventDefault()}>
      <label>
        搜索
        <input
          value={draft}
          maxLength={80}
          placeholder={kind === 'conversation' ? '标题、问题或已完成回答' : '主题、目标、题干或已提交反馈'}
          onChange={(event) => onDraft(event.target.value)}
        />
      </label>
      {kind === 'conversation' ? (
        <label>
          模式
          <select value={filters.mode ?? ''} onChange={(event) => onChange({ mode: event.target.value })}>
            {CONVERSATION_MODES.map(([value, label]) => <option key={value || 'all'} value={value}>{label}</option>)}
          </select>
        </label>
      ) : (
        <label>
          目标类型
          <select value={filters.goalType ?? ''} onChange={(event) => onChange({ goalType: event.target.value })}>
            <option value="">全部目标</option>
            <option value="CUSTOM">自定义目标</option>
          </select>
        </label>
      )}
      <label>
        状态
        <select value={filters.status ?? ''} onChange={(event) => onChange({ status: event.target.value })}>
          {(kind === 'conversation' ? CONVERSATION_STATUSES : LEARNING_STATUSES).map(([value, label]) => (
            <option key={value || 'all'} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        来源
        <select value={filters.sourceStatus ?? ''} onChange={(event) => onChange({ sourceStatus: event.target.value })}>
          {(kind === 'conversation' ? CONVERSATION_SOURCES : LEARNING_SOURCES).map(([value, label]) => (
            <option key={value || 'all'} value={value}>{label}</option>
          ))}
        </select>
      </label>
      <label>
        开始日期
        <input type="date" value={filters.dateFrom ?? ''} onChange={(event) => onChange({ dateFrom: event.target.value })} />
      </label>
      <label>
        结束日期
        <input type="date" value={filters.dateTo ?? ''} onChange={(event) => onChange({ dateTo: event.target.value })} />
      </label>
      {enabled ? <p className="history-filters__active">已启用：{enabled}</p> : null}
      {hasFilters(filters) ? <button className="quiet-button" type="button" onClick={onClear}>清除条件</button> : null}
    </form>
  )
}

function TrashConfirm({
  title,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="history-dialog" role="dialog" aria-modal="true" aria-labelledby="history-trash-title">
      <h2 id="history-trash-title">移入回收站</h2>
      <p>确定把「{title}」移入回收站？</p>
      <p>它会保留 30 天，之后可以从回收站恢复。文件和知识库不会被删除。</p>
      <div className="history-dialog__actions">
        <button className="quiet-button" type="button" onClick={onCancel} disabled={busy}>取消</button>
        <button type="button" onClick={onConfirm} disabled={busy}>{busy ? '正在移入' : '确认移入回收站'}</button>
      </div>
    </div>
  )
}

function PurgeConfirm({
  kind,
  title,
  busy,
  onCancel,
  onConfirm,
}: {
  kind: '对话' | '学习记录'
  title: string
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const [phrase, setPhrase] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const matches = phrase === '永久删除'

  useEffect(() => {
    inputRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [busy, onCancel])

  return (
    <div className="history-dialog" role="dialog" aria-modal="true" aria-labelledby="history-purge-title" aria-describedby="history-purge-description">
      <div className="history-dialog__heading">
        <h2 id="history-purge-title">确认永久删除</h2>
        <button className="quiet-button history-dialog__close" type="button" aria-label="关闭" onClick={onCancel} disabled={busy}>
          <X size={16} aria-hidden="true" />
        </button>
      </div>
      <p id="history-purge-description">将永久删除{kind}「{title}」。操作无法撤销；仅清除此{kind}，不会删除来源文件与知识库。</p>
      <p>请输入确认词“永久删除”后继续。</p>
      <form onSubmit={(event) => { event.preventDefault(); if (matches && !busy) onConfirm() }}>
        <label>
          确认词
          <input ref={inputRef} value={phrase} onChange={(event) => setPhrase(event.target.value)} placeholder="永久删除" autoComplete="off" />
        </label>
        <div className="history-dialog__actions">
          <button className="quiet-button" type="button" onClick={onCancel} disabled={busy}>取消</button>
          <button className="danger-button" type="submit" disabled={!matches || busy}>{busy ? '正在删除…' : '永久删除'}</button>
        </div>
      </form>
    </div>
  )
}

function isHistoryConflict(error: unknown): boolean {
  return error instanceof ApiError && [404, 409, 412].includes(error.status)
}

async function refreshHistoryViews() {
  await queryClient.invalidateQueries({ queryKey: ['conversation-history'] })
  await queryClient.invalidateQueries({ queryKey: ['learning-history'] })
  await queryClient.invalidateQueries({ queryKey: ['history-trash'] })
  await queryClient.invalidateQueries({ queryKey: ['home-overview'] })
  await queryClient.invalidateQueries({ queryKey: ['home-conversations'] })
  await queryClient.invalidateQueries({ queryKey: ['home-learning-recent'] })
}

function ConversationHistory({ trash }: { trash: boolean }) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = readFilters(searchParams, 'c')
  const filterKey = JSON.stringify(filters)
  const pager = usePagedItems<ConversationHistoryItem>(filterKey)
  const trashPager = usePagedItems<HistoryTrashItem>(trash ? 'conversation-trash' : 'conversation-live')
  const [draft, setDraft] = useState(filters.q ?? '')
  const [draftSource, setDraftSource] = useState(filters.q ?? '')
  if ((filters.q ?? '') !== draftSource) {
    setDraftSource(filters.q ?? '')
    setDraft(filters.q ?? '')
  }
  const [pending, setPending] = useState<ConversationHistoryItem | null>(null)
  const [pendingPurge, setPendingPurge] = useState<HistoryTrashItem | null>(null)
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)
  const openingRef = useRef('')
  const [openingId, setOpeningId] = useState('')
  const historyQuery = useQuery({
    queryKey: ['conversation-history', filterKey, pager.cursor ?? ''],
    queryFn: ({ signal }) => listConversationHistory(pager.cursor, 30, filters, { signal }),
    enabled: !trash,
    retry: false,
  })
  const trashQuery = useQuery({
    queryKey: ['history-trash', 'conversation', trashPager.cursor ?? ''],
    queryFn: ({ signal }) => listHistoryTrash('conversation', trashPager.cursor, 30, { signal }),
    enabled: trash,
    retry: false,
  })
  const activeQuery = trash ? trashQuery : historyQuery
  const pageItems = historyQuery.data?.items
  const visibleItems = pager.cursor ? pager.previous.concat(pageItems ?? []) : (pageItems ?? [])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (draft === (filters.q ?? '')) return
      const next = new URLSearchParams(searchParams)
      if (draft.trim()) next.set('cq', draft.trim())
      else next.delete('cq')
      setSearchParams(next, { replace: true })
    }, 300)
    return () => window.clearTimeout(handle)
  }, [draft, filters.q, searchParams, setSearchParams])

  const patch = (change: HistoryFilters) => {
    const next = new URLSearchParams(searchParams)
    const write = (key: string, value?: string) => {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if ('mode' in change) write('cmode', change.mode)
    if ('status' in change) write('cstatus', change.status)
    if ('sourceStatus' in change) write('csource', change.sourceStatus)
    if ('dateFrom' in change) write('cfrom', change.dateFrom)
    if ('dateTo' in change) write('cto', change.dateTo)
    setSearchParams(next, { replace: true })
  }

  const clearFilters = () => {
    const next = new URLSearchParams(searchParams)
    for (const key of ['cq', 'cmode', 'cstatus', 'csource', 'cfrom', 'cto']) next.delete(key)
    setSearchParams(next, { replace: true })
  }

  const openConversation = (conversationId: string) => {
    if (openingRef.current === conversationId) return
    openingRef.current = conversationId
    setOpeningId(conversationId)
    navigate(`/chat/${conversationId}`)
  }

  const confirmTrash = async () => {
    if (!pending?.row_version) return
    setBusy(true)
    setActionError('')
    try {
      await trashConversation(pending.conversation_id, pending.row_version)
      setPending(null)
      pager.reset()
      trashPager.reset()
      await refreshHistoryViews()
    } catch (error) {
      try {
        await historyQuery.refetch()
      } catch {
        // The next visible state still comes from the existing query cache.
      }
      setActionError(isHistoryConflict(error) ? '这条对话已经发生变化，列表已刷新，请重新确认。' : '移入回收站没有完成，列表已重新读取，请确认状态后重试。')
    } finally {
      setBusy(false)
    }
  }

  const restore = async (item: HistoryTrashItem) => {
    setBusy(true)
    setActionError('')
    try {
      await restoreConversation(item.object_id, item.row_version)
      trashPager.reset()
      pager.reset()
      await refreshHistoryViews()
    } catch (error) {
      try {
        await trashQuery.refetch()
      } catch {
        // The next visible state still comes from the existing query cache.
      }
      setActionError(isHistoryConflict(error) ? '这条对话已经发生变化，回收站列表已刷新。' : '恢复没有完成，回收站列表已重新读取，请确认状态后重试。')
    } finally {
      setBusy(false)
    }
  }

  const purge = async () => {
    if (!pendingPurge?.row_version) return
    setBusy(true)
    setActionError('')
    try {
      await purgeConversation(pendingPurge.object_id, pendingPurge.row_version)
      setPendingPurge(null)
      trashPager.reset()
      pager.reset()
      await refreshHistoryViews()
    } catch (error) {
      setPendingPurge(null)
      try {
        await trashQuery.refetch()
      } catch {
        // The next visible state still comes from the existing query cache.
      }
      setActionError(isHistoryConflict(error) ? '这条对话已经发生变化，回收站列表已刷新。' : '永久删除结果未知，回收站列表已重新读取；请确认记录状态后再操作。')
    } finally {
      setBusy(false)
    }
  }

  const conditionText = activeFilterText(filters, 'conversation')
  const trashPage = trashQuery.data?.items
  const trashItems = trashPager.cursor ? trashPager.previous.concat(trashPage ?? []) : (trashPage ?? [])

  return (
    <div className="history-panel">
      <p>{trash ? '回收站中的对话可以恢复为原来的会话，不会生成新回答。' : '打开已保存的对话不会重新生成回答。搜索包含标题、你的问题和已经完成的回答。'}</p>
      {!trash && filters.q && historyQuery.data?.search_index_status && historyQuery.data.search_index_status !== 'READY' ? (
        <p role="status">正文索引还在补齐，当前命中可能不完整。</p>
      ) : null}
      {trash ? null : (
        <FilterBar kind="conversation" filters={filters} draft={draft} onDraft={setDraft} onChange={patch} onClear={clearFilters} />
      )}
      {activeQuery.isLoading ? (
        <div className="history-state" role="status"><LoaderCircle className="spin" size={16} /> 正在加载对话历史</div>
      ) : null}
      {activeQuery.isError ? (
        <div className="history-state history-state--error" role="alert">
          <span>对话历史暂时读不出来。{conditionText ? `当前条件：${conditionText}。` : ''}</span>
          <button className="quiet-button" type="button" onClick={() => void activeQuery.refetch()}>重新加载</button>
        </div>
      ) : null}
      {actionError ? <div className="history-state history-state--error" role="alert">{actionError}</div> : null}
      {!trash && !historyQuery.isLoading && !historyQuery.isError && visibleItems.length === 0 ? (
        <div className="history-state">
          {conditionText
            ? `没有符合当前条件的对话。当前条件：${conditionText}。`
            : '还没有可阅读的对话。发送过的对话会保留在这里。'}
          {conditionText ? <button className="quiet-button" type="button" onClick={clearFilters}>清除条件</button> : null}
        </div>
      ) : null}
      {trash && !trashQuery.isLoading && !trashQuery.isError && trashItems.length === 0 ? (
        <div className="history-state">回收站里没有对话。</div>
      ) : null}
      <div className="history-list">
        {trash ? trashItems.map((item) => (
          <div className="history-item" key={item.object_id}>
            <span>
              <strong>{item.title || '未命名对话'}</strong>
              <small>会话 {item.object_id}</small>
              <small>移入时间 {formatTime(item.deleted_at)}</small>
            </span>
             <div className="history-item__actions">
               <button type="button" disabled={busy} onClick={() => void restore(item)}>恢复</button>
               <button className="danger-button" type="button" disabled={busy} onClick={() => setPendingPurge(item)}>永久删除</button>
             </div>
          </div>
        )) : visibleItems.map((item) => (
          <div className="history-item" key={item.conversation_id}>
            <button
              className="history-item__open"
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
            <HistoryHits kind="conversation" ownerId={item.conversation_id} keyword={filters.q ?? ''} locations={item.locations} />
            <button type="button" disabled={!item.row_version || busy} onClick={() => setPending(item)}>移入回收站</button>
          </div>
        ))}
      </div>
      {(trash ? trashQuery.data?.next_cursor : historyQuery.data?.next_cursor) ? (
        <button
          className="quiet-button"
          type="button"
          disabled={activeQuery.isFetching}
          onClick={() => {
            const next = trash ? trashQuery.data?.next_cursor : historyQuery.data?.next_cursor
            if (!next || activeQuery.isFetching) return
            if (trash) trashPager.showMore(next, trashItems)
            else pager.showMore(next, visibleItems)
          }}
        >
          {activeQuery.isFetching ? '正在加载更多' : '加载更多'}
        </button>
      ) : null}
      {pending ? (
        <TrashConfirm title={pending.title || pending.summary || '未命名对话'} busy={busy} onCancel={() => setPending(null)} onConfirm={() => void confirmTrash()} />
      ) : null}
      {pendingPurge ? (
        <PurgeConfirm kind="对话" title={pendingPurge.title || '未命名对话'} busy={busy} onCancel={() => setPendingPurge(null)} onConfirm={() => void purge()} />
      ) : null}
    </div>
  )
}

function LearningHistory({ trash }: { trash: boolean }) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = readFilters(searchParams, 'l')
  const filterKey = JSON.stringify(filters)
  const pager = usePagedItems<LearningHistoryItem>(filterKey)
  const trashPager = usePagedItems<HistoryTrashItem>(trash ? 'learning-trash' : 'learning-live')
  const [draft, setDraft] = useState(filters.q ?? '')
  const [draftSource, setDraftSource] = useState(filters.q ?? '')
  if ((filters.q ?? '') !== draftSource) {
    setDraftSource(filters.q ?? '')
    setDraft(filters.q ?? '')
  }
  const [pending, setPending] = useState<LearningHistoryItem | null>(null)
  const [pendingPurge, setPendingPurge] = useState<HistoryTrashItem | null>(null)
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)
  const openingRef = useRef('')
  const [openingId, setOpeningId] = useState('')
  const historyQuery = useQuery({
    queryKey: ['learning-history', filterKey, pager.cursor ?? ''],
    queryFn: ({ signal }) => listLearningHistory(pager.cursor, 30, filters, { signal }),
    enabled: !trash,
    retry: false,
  })
  const trashQuery = useQuery({
    queryKey: ['history-trash', 'learning_session', trashPager.cursor ?? ''],
    queryFn: ({ signal }) => listHistoryTrash('learning_session', trashPager.cursor, 30, { signal }),
    enabled: trash,
    retry: false,
  })
  const activeQuery = trash ? trashQuery : historyQuery
  const pageItems = historyQuery.data?.items
  const visibleItems = pager.cursor ? pager.previous.concat(pageItems ?? []) : (pageItems ?? [])

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (draft === (filters.q ?? '')) return
      const next = new URLSearchParams(searchParams)
      if (draft.trim()) next.set('lq', draft.trim())
      else next.delete('lq')
      setSearchParams(next, { replace: true })
    }, 300)
    return () => window.clearTimeout(handle)
  }, [draft, filters.q, searchParams, setSearchParams])

  const patch = (change: HistoryFilters) => {
    const next = new URLSearchParams(searchParams)
    const write = (key: string, value?: string) => {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if ('goalType' in change) write('lgoal', change.goalType)
    if ('status' in change) write('lstatus', change.status)
    if ('sourceStatus' in change) write('lsource', change.sourceStatus)
    if ('dateFrom' in change) write('lfrom', change.dateFrom)
    if ('dateTo' in change) write('lto', change.dateTo)
    setSearchParams(next, { replace: true })
  }

  const clearFilters = () => {
    const next = new URLSearchParams(searchParams)
    for (const key of ['lq', 'lgoal', 'lstatus', 'lsource', 'lfrom', 'lto']) next.delete(key)
    setSearchParams(next, { replace: true })
  }

  const openSession = (item: LearningHistoryItem) => {
    const learningSessionId = item.learning_session_id
    if (openingRef.current === learningSessionId) return
    openingRef.current = learningSessionId
    setOpeningId(learningSessionId)
    navigate(
      item.status === 'COMPLETED'
        ? `/learning/session/${learningSessionId}?focus=summary`
        : `/learning/session/${learningSessionId}`,
    )
  }

  const confirmTrash = async () => {
    if (!pending?.row_version) return
    setBusy(true)
    setActionError('')
    try {
      await trashLearningSession(pending.learning_session_id, pending.row_version)
      setPending(null)
      pager.reset()
      trashPager.reset()
      await refreshHistoryViews()
    } catch (error) {
      try {
        await historyQuery.refetch()
      } catch {
        // The next visible state still comes from the existing query cache.
      }
      setActionError(isHistoryConflict(error) ? '这条学习记录已经发生变化，列表已刷新，请重新确认。' : '移入回收站没有完成，列表已重新读取，请确认状态后重试。')
    } finally {
      setBusy(false)
    }
  }

  const restore = async (item: HistoryTrashItem) => {
    setBusy(true)
    setActionError('')
    try {
      await restoreLearningSession(item.object_id, item.row_version)
      trashPager.reset()
      pager.reset()
      await refreshHistoryViews()
    } catch (error) {
      try {
        await trashQuery.refetch()
      } catch {
        // The next visible state still comes from the existing query cache.
      }
      setActionError(isHistoryConflict(error) ? '这条学习记录已经发生变化，回收站列表已刷新。' : '恢复没有完成，回收站列表已重新读取，请确认状态后重试。')
    } finally {
      setBusy(false)
    }
  }

  const purge = async () => {
    if (!pendingPurge?.row_version) return
    setBusy(true)
    setActionError('')
    try {
      await purgeLearningSession(pendingPurge.object_id, pendingPurge.row_version)
      setPendingPurge(null)
      trashPager.reset()
      pager.reset()
      await refreshHistoryViews()
    } catch (error) {
      setPendingPurge(null)
      try {
        await trashQuery.refetch()
      } catch {
        // The next visible state still comes from the existing query cache.
      }
      setActionError(isHistoryConflict(error) ? '这条学习记录已经发生变化，回收站列表已刷新。' : '永久删除结果未知，回收站列表已重新读取；请确认记录状态后再操作。')
    } finally {
      setBusy(false)
    }
  }

  const conditionText = activeFilterText(filters, 'learning')
  const trashPage = trashQuery.data?.items
  const trashItems = trashPager.cursor ? trashPager.previous.concat(trashPage ?? []) : (trashPage ?? [])

  return (
    <div className="history-panel">
      <p>{trash ? '回收站中的学习记录可以恢复为原来的会话，不会重新出题。' : '打开已保存的学习会话不会重新出题，也不会自动提交答案。搜索包含主题、目标、题干和已经提交的答案与反馈。'}</p>
      {!trash && filters.q && historyQuery.data?.search_index_status && historyQuery.data.search_index_status !== 'READY' ? (
        <p role="status">正文索引还在补齐，当前命中可能不完整。</p>
      ) : null}
      {trash ? null : (
        <FilterBar kind="learning" filters={filters} draft={draft} onDraft={setDraft} onChange={patch} onClear={clearFilters} />
      )}
      {activeQuery.isLoading ? (
        <div className="history-state" role="status"><LoaderCircle className="spin" size={16} /> 正在加载学习历史</div>
      ) : null}
      {activeQuery.isError ? (
        <div className="history-state history-state--error" role="alert">
          <span>学习历史暂时读不出来。{conditionText ? `当前条件：${conditionText}。` : ''}</span>
          <button className="quiet-button" type="button" onClick={() => void activeQuery.refetch()}>重新加载</button>
        </div>
      ) : null}
      {actionError ? <div className="history-state history-state--error" role="alert">{actionError}</div> : null}
      {!trash && !historyQuery.isLoading && !historyQuery.isError && visibleItems.length === 0 ? (
        <div className="history-state">
          {conditionText
            ? `没有符合当前条件的学习记录。当前条件：${conditionText}。`
            : '还没有可找回的学习会话。从知识库开始的一题会保留在这里。'}
          {conditionText ? <button className="quiet-button" type="button" onClick={clearFilters}>清除条件</button> : null}
        </div>
      ) : null}
      {trash && !trashQuery.isLoading && !trashQuery.isError && trashItems.length === 0 ? (
        <div className="history-state">回收站里没有学习记录。</div>
      ) : null}
      <div className="history-list">
        {trash ? trashItems.map((item) => (
          <div className="history-item" key={item.object_id}>
            <span>
              <strong>{item.title || '未命名学习'}</strong>
              <small>会话 {item.object_id}</small>
              <small>移入时间 {formatTime(item.deleted_at)}</small>
            </span>
             <div className="history-item__actions">
               <button type="button" disabled={busy} onClick={() => void restore(item)}>恢复</button>
               <button className="danger-button" type="button" disabled={busy} onClick={() => setPendingPurge(item)}>永久删除</button>
             </div>
          </div>
        )) : visibleItems.map((item) => (
          <div className="history-item" key={item.learning_session_id}>
            <button
              className="history-item__open"
              type="button"
              disabled={openingId === item.learning_session_id}
              onClick={() => openSession(item)}
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
                {item.status === 'COMPLETED' ? <em>查看总结</em> : null}
                <em>{formatTime(item.updated_at)}</em>
              </span>
              {openingId === item.learning_session_id ? <span>正在打开</span> : <History size={14} aria-hidden="true" />}
            </button>
            <HistoryHits kind="learning" ownerId={item.learning_session_id} keyword={filters.q ?? ''} locations={item.locations} />
            <button type="button" disabled={!item.row_version || busy} onClick={() => setPending(item)}>移入回收站</button>
          </div>
        ))}
      </div>
      {(trash ? trashQuery.data?.next_cursor : historyQuery.data?.next_cursor) ? (
        <button
          className="quiet-button"
          type="button"
          disabled={activeQuery.isFetching}
          onClick={() => {
            const next = trash ? trashQuery.data?.next_cursor : historyQuery.data?.next_cursor
            if (!next || activeQuery.isFetching) return
            if (trash) trashPager.showMore(next, trashItems)
            else pager.showMore(next, visibleItems)
          }}
        >
          {activeQuery.isFetching ? '正在加载更多' : '加载更多'}
        </button>
      ) : null}
      {pending ? (
        <TrashConfirm title={pending.topic || '未命名学习'} busy={busy} onCancel={() => setPending(null)} onConfirm={() => void confirmTrash()} />
      ) : null}
      {pendingPurge ? (
        <PurgeConfirm kind="学习记录" title={pendingPurge.title || '未命名学习'} busy={busy} onCancel={() => setPendingPurge(null)} onConfirm={() => void purge()} />
      ) : null}
    </div>
  )
}

export default function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const learningTab = searchParams.get('tab') === 'learning'
  const trash = searchParams.get('view') === 'trash'

  const selectTab = (tab: 'conversations' | 'learning') => {
    const next = new URLSearchParams(searchParams)
    if (tab === 'learning') next.set('tab', 'learning')
    else next.delete('tab')
    setSearchParams(next, { replace: true })
  }

  const toggleTrash = () => {
    const next = new URLSearchParams(searchParams)
    if (trash) next.delete('view')
    else next.set('view', 'trash')
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
        <div className="history-heading-actions">
          <button className="quiet-button" type="button" onClick={toggleTrash}>{trash ? '返回历史' : '查看回收站'}</button>
          <Link className="quiet-button" to={learningTab ? '/learning' : '/chat'}>
            {learningTab ? '返回学习' : '返回对话'}
          </Link>
        </div>
      </header>
      <div className="history-tabs" role="tablist" aria-label="历史类型">
        <button className={`history-tab ${learningTab ? '' : 'history-tab--active'}`} type="button" role="tab" aria-selected={!learningTab} onClick={() => selectTab('conversations')}>对话历史</button>
        <button className={`history-tab ${learningTab ? 'history-tab--active' : ''}`} type="button" role="tab" aria-selected={learningTab} onClick={() => selectTab('learning')}>学习历史</button>
      </div>
      {learningTab ? <LearningHistory trash={trash} /> : <ConversationHistory trash={trash} />}
    </section>
  )
}
