import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import KnowledgeBaseRetrievalPanel from '../components/KnowledgeBaseRetrievalPanel'
import type { KnowledgeBaseItem, RetrievalTestResponse } from '../api/knowledgeBases'

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  })
}

const baseItem: KnowledgeBaseItem = {
  knowledge_base_id: 'kb-retrieval',
  name: '检索测试库',
  description: '本地测试',
  icon: 'book-open',
  color: '#176b87',
  status: 'READY',
  file_count: 2,
  available_file_count: 2,
  duplicate_name: false,
  created_at: '2026-09-24T00:00:00Z',
  updated_at: '2026-09-24T00:00:00Z',
  deleted_at: null,
  purge_after: null,
  row_version: 1,
}

const candidate = {
  chunk_id: 'chunk-1',
  file_id: 'file-1',
  file_name: '课程资料<script>window.__retrievalXss = true</script>.txt',
  location: {
    sequence_number: 1,
    heading_path: ['第一章', '<img src=x onerror=alert(1)>'],
    page_start: 3,
    page_end: 4,
    slide_number: null,
    line_start: null,
    line_end: null,
    source_kind: 'pdf_page',
  },
  excerpt: '<img src=x onerror=alert(1)> 向量数据库用于存储和检索向量。',
  rank: 1,
  fts_rank: 1,
  bm25: -0.42,
  vector_rank: 2,
  cosine_distance: 0.08,
  cosine_similarity: 0.92,
  rrf_score: 0.03,
  exact_match_bonus: 0.001,
  diversity_adjustment: 0,
  ranking_score: 0.031,
  exact_match_fields: ['content'],
  ranking_reasons: ['RRF_FTS', 'RRF_VECTOR'],
}

function retrievalResponse(overrides: Partial<RetrievalTestResponse> = {}): RetrievalTestResponse {
  return {
    knowledge_base_id: baseItem.knowledge_base_id,
    index_version_id: 'index-1',
    status: 'supported',
    question_type: 'definition',
    ranking_algorithm_version: 'rrf-exact-diversity-v1',
    evidence_rules_version: 'evidence-gate-v1',
    rank_constant: 60,
    final_candidate_limit: 8,
    distinct_source_count: 1,
    reason_codes: ['SUPPORTING_CANDIDATE_FOUND'],
    retrieval_error_code: null,
    retrieval_error_route: null,
    candidates: [candidate],
    local_message: null,
    suggestions: [],
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function installRetrievalFetch(handler: (question: string, callIndex: number) => Promise<Response> | Response) {
  const retrievalCalls: Array<{ question: string; signal?: AbortSignal | null }> = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/system/session')) return response({ status: 'ready' })
    if (url.endsWith('/api/v1/health')) return response({ status: 'ok', version: '0.1.0' })
    if (url.endsWith('/api/v1/knowledge-bases/kb-retrieval')) return response(baseItem)
    if (url.endsWith('/api/v1/knowledge-bases/kb-retrieval/files')) return response({ items: [] })
    if (url.includes('/api/v1/files?sort=name')) return response({ items: [], next_cursor: null })
    if (url.includes('/retrieval-tests')) {
      const body = JSON.parse(String(init?.body)) as { question: string }
      retrievalCalls.push({ question: body.question, signal: init?.signal })
      return handler(body.question, retrievalCalls.length)
    }
    return response({ status: 'ok', version: '0.1.0' })
  }))
  return retrievalCalls
}

describe('stage 5 local retrieval test panel', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('renders bounded candidates, real locations and ranking signals as plain text', async () => {
    const calls = installRetrievalFetch(() => response(retrievalResponse({ candidates: Array.from({ length: 8 }, (_, index) => ({ ...candidate, chunk_id: `chunk-${index}`, file_name: `资料-${index}.txt`, rank: index + 1 })) })))
    render(<KnowledgeBaseRetrievalPanel item={baseItem} />)

    const input = screen.getByRole('textbox', { name: '测试问题' })
    expect(screen.getByRole('button', { name: '测试检索' })).toBeDisabled()
    fireEvent.change(input, { target: { value: '向量数据库是什么？' } })
    fireEvent.click(screen.getByRole('button', { name: '测试检索' }))

    expect(await screen.findByText('找到可能支持的资料')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: /资料-\d+\.txt/ })).toHaveLength(8)
    expect(screen.getAllByText('页码：3-4 页')).toHaveLength(8)
    expect(screen.getAllByText('来源：PDF 页')).toHaveLength(8)
    expect(screen.getAllByText(/余弦相似度 0\.920000/)).toHaveLength(8)
    expect(screen.getAllByText('<img src=x onerror=alert(1)> 向量数据库用于存储和检索向量。')).toHaveLength(8)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
    expect(calls).toHaveLength(1)
    const body = (await (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.find((call) => String(call[0]).includes('/retrieval-tests'))?.[1])
    expect(JSON.parse(String(body.body))).toEqual({ question: '向量数据库是什么？' })
  })

  it.each([
    ['insufficient', '资料不足', retrievalResponse({ status: 'insufficient', index_version_id: null, candidates: [], reason_codes: ['EMPTY_RESULTS'], local_message: '当前资料不足。' })],
    ['unavailable without active index', '检索暂不可用', retrievalResponse({ status: 'unavailable', index_version_id: null, candidates: [], retrieval_error_code: 'INDEX_VERSION_NOT_AVAILABLE', retrieval_error_route: 'scope', reason_codes: ['INDEX_VERSION_NOT_AVAILABLE'] })],
    ['unavailable with missing model', '检索暂不可用', retrievalResponse({ status: 'unavailable', candidates: [], retrieval_error_code: 'MODEL_MISSING_OFFLINE', retrieval_error_route: 'embedding', reason_codes: ['MODEL_MISSING_OFFLINE'] })],
  ])('distinguishes %s from a supported result', async (_caseName, label, result) => {
    installRetrievalFetch(() => response(result))
    render(<KnowledgeBaseRetrievalPanel item={baseItem} />)
    fireEvent.change(screen.getByRole('textbox', { name: '测试问题' }), { target: { value: '测试问题' } })
    fireEvent.click(screen.getByRole('button', { name: '测试检索' }))

    expect(await screen.findByText(label)).toBeInTheDocument()
    if (result.status === 'unavailable') {
      expect(screen.queryByText('资料不足')).not.toBeInTheDocument()
    }
  })

  it('keeps the input for retry, blocks duplicate clicks and reports an empty result', async () => {
    const request = deferred<Response>()
    const calls = installRetrievalFetch(() => request.promise)
    render(<KnowledgeBaseRetrievalPanel item={baseItem} />)
    const input = screen.getByRole('textbox', { name: '测试问题' })
    fireEvent.change(input, { target: { value: '没有命中的问题' } })
    const submit = screen.getByRole('button', { name: '测试检索' })
    fireEvent.click(submit)
    expect(await screen.findByText('正在查询当前活动索引…')).toBeInTheDocument()
    fireEvent.click(submit)
    expect(calls).toHaveLength(1)
    request.resolve(response(retrievalResponse({ status: 'insufficient', candidates: [], reason_codes: ['EMPTY_RESULTS'], local_message: '没有足够资料。' })))
    expect(await screen.findByText('资料不足')).toBeInTheDocument()
    expect(screen.getByDisplayValue('没有命中的问题')).toBeInTheDocument()
    expect(screen.getByText('没有可展示的候选资料')).toBeInTheDocument()
  })

  it('ignores an older response after the question changes and a newer request completes', async () => {
    const first = deferred<Response>()
    const second = deferred<Response>()
    const calls = installRetrievalFetch((_question, callIndex) => callIndex === 1 ? first.promise : second.promise)
    render(<KnowledgeBaseRetrievalPanel item={baseItem} />)
    const input = screen.getByRole('textbox', { name: '测试问题' })
    fireEvent.change(input, { target: { value: '第一个问题' } })
    fireEvent.click(screen.getByRole('button', { name: '测试检索' }))
    fireEvent.change(input, { target: { value: '第二个问题' } })
    fireEvent.click(screen.getByRole('button', { name: '测试检索' }))
    await waitFor(() => expect(calls).toHaveLength(2))
    second.resolve(response(retrievalResponse({ candidates: [{ ...candidate, file_name: '新结果.txt' }] })))
    expect(await screen.findByText('新结果.txt')).toBeInTheDocument()
    first.resolve(response(retrievalResponse({ candidates: [{ ...candidate, file_name: '旧结果.txt' }] })))
    await waitFor(() => expect(screen.queryByText('旧结果.txt')).not.toBeInTheDocument())
    expect(screen.getByDisplayValue('第二个问题')).toBeInTheDocument()
  })

  it('drops an in-flight response when the knowledge base id changes', async () => {
    const first = deferred<Response>()
    const second = deferred<Response>()
    const calls = installRetrievalFetch((_question, callIndex) => callIndex === 1 ? first.promise : second.promise)
    const { rerender } = render(<KnowledgeBaseRetrievalPanel key="kb-retrieval" item={baseItem} />)
    fireEvent.change(screen.getByRole('textbox', { name: '测试问题' }), { target: { value: '旧知识库问题' } })
    fireEvent.click(screen.getByRole('button', { name: '测试检索' }))
    rerender(<KnowledgeBaseRetrievalPanel key="kb-other" item={{ ...baseItem, knowledge_base_id: 'kb-other', name: '另一个库' }} />)
    fireEvent.change(screen.getByRole('textbox', { name: '测试问题' }), { target: { value: '新知识库问题' } })
    fireEvent.click(screen.getByRole('button', { name: '测试检索' }))
    await waitFor(() => expect(calls).toHaveLength(2))
    second.resolve(response(retrievalResponse({ knowledge_base_id: 'kb-other', candidates: [{ ...candidate, file_name: '新知识库资料.txt' }] })))
    expect(await screen.findByText('新知识库资料.txt')).toBeInTheDocument()
    first.resolve(response(retrievalResponse({ candidates: [{ ...candidate, file_name: '旧知识库资料.txt' }] })))
    await waitFor(() => expect(screen.queryByText('旧知识库资料.txt')).not.toBeInTheDocument())
  })

  it('keeps a transport error separate from资料不足 and retries with the same question', async () => {
    let attempt = 0
    const calls = installRetrievalFetch(() => {
      attempt += 1
      if (attempt === 1) return response({ detail: '本地服务暂时不可用。', code: 'SERVICE_UNAVAILABLE' }, 503)
      return response(retrievalResponse({ candidates: [{ ...candidate, file_name: '重试成功.txt' }] }))
    })
    render(<KnowledgeBaseRetrievalPanel item={baseItem} />)
    const input = screen.getByRole('textbox', { name: '测试问题' })
    fireEvent.change(input, { target: { value: '请求失败后重试' } })
    fireEvent.click(screen.getByRole('button', { name: '测试检索' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('本地服务暂时不可用。')
    expect(screen.getByDisplayValue('请求失败后重试')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByText('重试成功.txt')).toBeInTheDocument()
    expect(calls).toHaveLength(2)
  })
})
