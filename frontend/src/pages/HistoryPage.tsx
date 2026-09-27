import { useEffect, useRef, useState } from 'react'
import { GraduationCap, History, LoaderCircle, MessageSquare } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import {
  listConversationHistory,
  listHistoryTrash,
  listLearningHistory,
  restoreConversation,
  restoreLearningSession,
  trashConversation,
  trashLearningSession,
  type ConversationHistoryItem,
  type HistoryFilters,
  type HistoryTrashItem,
  type LearningHistoryItem,
} from '../api/history'
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
          placeholder={kind === 'conversation' ? '标题或已保存摘要' : '学习主题或目标'}
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
      <div>
        <button className="quiet-button" type="button" onClick={onCancel} disabled={busy}>取消</button>
        <button type="button" onClick={onConfirm} disabled={busy}>{busy ? '正在移入' : '确认移入回收站'}</button>
      </div>
    </div>
  )
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
    } catch {
      setActionError('移入回收站没有完成，请重试。')
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
    } catch {
      setActionError('恢复没有完成，请重试。')
    } finally {
      setBusy(false)
    }
  }

  const conditionText = activeFilterText(filters, 'conversation')
  const trashPage = trashQuery.data?.items
  const trashItems = trashPager.cursor ? trashPager.previous.concat(trashPage ?? []) : (trashPage ?? [])

  return (
    <div className="history-panel">
      <p>{trash ? '回收站中的对话可以恢复为原来的会话，不会生成新回答。' : '打开已保存的对话不会重新生成回答。搜索只匹配标题和列表里的摘要。'}</p>
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
            <button type="button" disabled={busy} onClick={() => void restore(item)}>恢复</button>
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
                {item.locations?.map((location) => (
                  <small key={`${location.section}-${location.snippet}`}>命中{location.section === 'title' ? '标题' : '摘要'}：{location.snippet}</small>
                ))}
                <small>会话 {item.conversation_id}</small>
              </span>
              <span className="history-item__meta">
                <em>{modeLabel(item.current_mode)}{item.scope_name ? ` · ${item.scope_name}` : ''}</em>
                <em>{statusLabel(item.status)} · {sourceStatusLabel(item.source_status)}</em>
                <em>{formatTime(item.updated_at)} · {item.message_count} 条消息</em>
              </span>
              {openingId === item.conversation_id ? <span>正在打开</span> : <History size={14} aria-hidden="true" />}
            </button>
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

  const openSession = (learningSessionId: string) => {
    if (openingRef.current === learningSessionId) return
    openingRef.current = learningSessionId
    setOpeningId(learningSessionId)
    navigate(`/learning/session/${learningSessionId}`)
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
    } catch {
      setActionError('移入回收站没有完成，请重试。')
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
    } catch {
      setActionError('恢复没有完成，请重试。')
    } finally {
      setBusy(false)
    }
  }

  const conditionText = activeFilterText(filters, 'learning')
  const trashPage = trashQuery.data?.items
  const trashItems = trashPager.cursor ? trashPager.previous.concat(trashPage ?? []) : (trashPage ?? [])

  return (
    <div className="history-panel">
      <p>{trash ? '回收站中的学习记录可以恢复为原来的会话，不会重新出题。' : '打开已保存的学习会话不会重新出题，也不会自动提交答案。搜索只匹配主题和目标。'}</p>
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
            <button type="button" disabled={busy} onClick={() => void restore(item)}>恢复</button>
          </div>
        )) : visibleItems.map((item) => (
          <div className="history-item" key={item.learning_session_id}>
            <button
              className="history-item__open"
              type="button"
              disabled={openingId === item.learning_session_id}
              onClick={() => openSession(item.learning_session_id)}
            >
              <GraduationCap size={16} aria-hidden="true" />
              <span>
                <strong>{item.topic || '未命名学习'}</strong>
                <small>{item.scope_name ?? '资料范围不可用'} · {item.scope_file_count} 个文件</small>
                {item.locations?.map((location) => (
                  <small key={`${location.section}-${location.snippet}`}>命中{location.section === 'topic' ? '主题' : '目标'}：{location.snippet}</small>
                ))}
                <small>会话 {item.learning_session_id}</small>
              </span>
              <span className="history-item__meta">
                <em>{learningStatusLabel(item.status, item.answered_count)} · {sourceStatusLabel(item.source_status)}</em>
                <em>已作答 {item.answered_count} / {item.target_question_count}</em>
                <em>{formatTime(item.updated_at)}</em>
              </span>
              {openingId === item.learning_session_id ? <span>正在打开</span> : <History size={14} aria-hidden="true" />}
            </button>
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
