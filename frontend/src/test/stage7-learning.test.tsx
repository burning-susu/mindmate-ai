import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import App from '../App'
import { queryClient } from '../queryClient'

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  })
}

const knowledgeBase = {
  knowledge_base_id: 'kb-1',
  name: '固定资料主库',
  description: null,
  icon: 'book-open',
  color: '#176b87',
  status: 'READY',
  file_count: 1,
  available_file_count: 1,
  duplicate_name: false,
  created_at: '2026-09-26T00:00:00Z',
  updated_at: '2026-09-26T00:00:00Z',
  deleted_at: null,
  purge_after: null,
  row_version: 2,
}

const emptyIndexStatus = {
  knowledge_base_id: 'kb-1',
  status: 'READY',
  active_index_version_id: 'index-1',
  active_index_version_status: 'READY',
  target_index_version_id: null,
  target_index_version_status: null,
  target_stage: null,
  file_counts: { total: 1, available: 1, processing: 0, failed: 0 },
  failures: [],
  tasks: [],
  embedding_model_state: 'READY',
  embedding_model_error_code: null,
  operation_in_progress: false,
  can_retry_failed: false,
  can_rebuild: true,
}

const embeddingModel = {
  state: 'READY',
  phase: 'READY',
  base_model_id: 'BAAI/bge-small-zh-v1.5',
  base_model_url: 'https://example.invalid/base',
  artifact_repository_id: 'Xenova/bge-small-zh-v1.5',
  artifact_url: 'https://example.invalid/onnx',
  license: 'MIT',
  base_revision: 'base',
  artifact_revision: 'onnx',
  artifact_fingerprint: 'a'.repeat(64),
  total_size_bytes: 1,
  downloaded_bytes: 1,
  current_file: null,
  file_downloaded_bytes: null,
  file_size_bytes: null,
  task_id: null,
  diagnostic_id: null,
  error_code: null,
  can_install: false,
  can_cancel: false,
}

function question(feedback: unknown = null) {
  return {
    question_id: 'question-1',
    learning_session_id: 'session-1',
    question_type: 'SINGLE_CHOICE',
    prompt_text: '资料里的超时时间是多少？',
    options: [
      { option_id: 'opt-a', label: '12 秒' },
      { option_id: 'opt-b', label: '30 秒' },
      { option_id: 'opt-c', label: '47 秒' },
      { option_id: 'opt-d', label: '90 秒' },
    ],
    sequence_number: 1,
    status: feedback ? 'ANSWERED' : 'OPEN',
    difficulty: 'BASIC',
    row_version: 1,
    feedback,
  }
}

function session(overrides: Record<string, unknown> = {}) {
  return {
    learning_session_id: 'session-1',
    topic: 'API 单次请求超时',
    goal_type: 'CUSTOM',
    goal_text: '记住唯一超时值',
    knowledge_base_id: 'kb-1',
    target_question_count: 1,
    status: 'IN_PROGRESS',
    failure_code: null,
    failure_detail: null,
    completed_question_count: 0,
    current_question_id: 'question-1',
    provider: 'mock',
    model: 'learning-demo-fixture-v1',
    live_model_called: false,
    row_version: 1,
    created_at: '2026-09-26T00:00:00Z',
    started_at: '2026-09-26T00:00:00Z',
    scope: {
      knowledge_base_id: 'kb-1',
      index_version_id: 'index-1',
      source_set_hash: 'hash',
      file_ids: ['file-1'],
    },
    plan: {
      learning_plan_id: 'plan-1',
      status: 'READY',
      target_question_count: 1,
      knowledge_point_title: '超时时间',
      prompt_template_version: 'learning-demo-fixture-v1',
    },
    question: question(),
    ...overrides,
  }
}

function feedback(result: 'CORRECT' | 'INCORRECT') {
  const correct = result === 'CORRECT'
  return {
    feedback_id: 'feedback-1',
    attempt_id: 'attempt-1',
    selected_option: correct ? 'opt-b' : 'opt-a',
    result,
    explanation: correct
      ? '所选「30 秒」与资料记载一致。依据见引用 [1]。此反馈来自本地 Mock 确定性演示，不是在线模型生成。'
      : '所选「12 秒」与资料记载不一致。资料记载的数值是「30 秒」。依据见引用 [1]。此反馈来自本地 Mock 确定性演示，不是在线模型生成。',
    provider: 'mock',
    model: 'learning-demo-fixture-v1',
    live_model_called: false,
    citations: [{
      citation_id: 'citation-1',
      display_number: 1,
      file_name: '服务超时策略.txt',
      file_id: 'file-1',
      chunk_id: 'chunk-1',
      line_start: 1,
      line_end: 12,
      page_start: null,
      page_end: null,
      excerpt: 'API 单次请求超时为 30 秒。持久任务不使用这个请求超时值。',
      source_status: 'AVAILABLE',
      can_open_source: true,
    }],
  }
}

function renderAt(path: string) {
  window.history.pushState({}, '', path)
  return render(<BrowserRouter><App /></BrowserRouter>)
}

describe.sequential('stage 7 learning demo', () => {
  afterEach(() => {
    queryClient.clear()
    vi.unstubAllGlobals()
  })

  it('does not create a session while the start page is blank or the knowledge base is unavailable', async () => {
    const posts: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (init?.method === 'POST') posts.push(url)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1/files')) return response({ items: [{ file_id: 'file-1', display_name: '服务超时策略.txt', document_type: 'TXT', file_status: 'PARSED', membership_status: 'ACTIVE', index_state: 'READY', available_for_retrieval: true, added_at: '2026-09-26T00:00:00Z', knowledge_base_file_id: 'member-1' }] })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response({ ...knowledgeBase, status: 'PREPARING', available_file_count: 0 })
      return response({ status: 'ok', version: '0.1.0' })
    }))

    renderAt('/learning/new?knowledge_base_id=kb-1')
    expect(await screen.findByRole('heading', { name: '基于知识库的一题演示' })).toBeInTheDocument()
    expect(screen.getByText('本地规则模拟演示，未调用真实 DeepSeek。学习出题不读取聊天设置里的在线模式。')).toBeInTheDocument()
    expect(await screen.findByText('服务超时策略.txt')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建并开始' })).toBeDisabled()
    fireEvent.change(screen.getByRole('textbox', { name: '学习主题' }), { target: { value: '   ' } })
    fireEvent.change(screen.getByRole('textbox', { name: '学习目标' }), { target: { value: '记住' } })
    expect(screen.getByRole('button', { name: '创建并开始' })).toBeDisabled()
    expect(posts.some((url) => url.includes('/learning-sessions'))).toBe(false)
    expect(screen.queryByText('answer_key')).not.toBeInTheDocument()
  })

  it('creates one session from a ready knowledge base and keeps the same request id', async () => {
    const bodies: unknown[] = []
    const keys: string[] = []
    let releaseCreate: ((value: Response) => void) | undefined
    const created = session()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1/files')) return response({ items: [] })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(knowledgeBase)
      if (url.endsWith('/api/v1/learning-sessions') && init?.method === 'POST') {
        bodies.push(JSON.parse(String(init.body)))
        keys.push(new Headers(init.headers).get('Idempotency-Key') ?? '')
        return new Promise<Response>((resolve) => { releaseCreate = resolve })
      }
      if (url.endsWith('/api/v1/learning-sessions/session-1')) return response(created)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    renderAt('/learning/new?knowledge_base_id=kb-1')
    fireEvent.change(await screen.findByRole('textbox', { name: '学习主题' }), { target: { value: 'API 单次请求超时' } })
    fireEvent.change(screen.getByRole('textbox', { name: '学习目标' }), { target: { value: '记住唯一超时值' } })
    const button = screen.getByRole('button', { name: '创建并开始' })
    fireEvent.click(button)
    fireEvent.click(button)
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({
      knowledge_base_id: 'kb-1',
      topic: 'API 单次请求超时',
      goal_text: '记住唯一超时值',
      goal_type: 'CUSTOM',
      target_question_count: 1,
      client_request_id: keys[0],
    })
    releaseCreate?.(response(created))
    expect(await screen.findByRole('heading', { name: 'API 单次请求超时' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/learning/session/session-1')
  })

  it('offers learning from a ready knowledge base without creating a session', async () => {
    const posts: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (init?.method === 'POST' && !url.includes('/system/session')) posts.push(url)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/index-status')) return response(emptyIndexStatus)
      if (url.endsWith('/embedding-model')) return response(embeddingModel)
      if (url.endsWith('/api/v1/knowledge-bases/kb-1/files')) return response({ items: [] })
      if (url.includes('/api/v1/files?sort=name')) return response({ items: [], next_cursor: null })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(knowledgeBase)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    renderAt('/knowledge-bases/kb-1')
    fireEvent.click(await screen.findByRole('button', { name: '基于此知识库学习' }))
    expect(await screen.findByRole('heading', { name: '基于知识库的一题演示' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/learning/new')
    expect(posts.some((url) => url.includes('/learning-sessions'))).toBe(false)
  })

  it('hides the answer, blocks an empty choice, and ignores a repeated submit', async () => {
    let attemptCalls = 0
    let releaseAttempt: ((value: Response) => void) | undefined
    const answered = feedback('INCORRECT')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(knowledgeBase)
      if (url.includes('/attempts') && init?.method === 'POST') {
        attemptCalls += 1
        return new Promise<Response>((resolve) => { releaseAttempt = resolve })
      }
      if (url.endsWith('/api/v1/learning-sessions/session-1')) {
        return response(attemptCalls > 0 ? session({ question: question(answered), completed_question_count: 1 }) : session())
      }
      return response({ status: 'ok', version: '0.1.0' })
    }))

    renderAt('/learning/session/session-1')
    expect(await screen.findByText('资料里的超时时间是多少？')).toBeInTheDocument()
    expect(screen.queryByText('持久任务不使用这个请求超时值')).not.toBeInTheDocument()
    expect(screen.queryByText(/与资料记载/)).not.toBeInTheDocument()
    expect(screen.queryByText('answer_key')).not.toBeInTheDocument()
    expect(screen.queryByText('EXACT_OPTION')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '提交答案' })).toBeDisabled()
    fireEvent.click(screen.getByRole('radio', { name: '12 秒' }))
    const submit = screen.getByRole('button', { name: '提交答案' })
    fireEvent.click(submit)
    fireEvent.click(submit)
    await waitFor(() => expect(attemptCalls).toBe(1))
    releaseAttempt?.(response(answered))
    expect(await screen.findByText('结果：不正确')).toBeInTheDocument()
    expect(screen.getByText(/资料记载的数值是「30 秒」/)).toBeInTheDocument()
  })

  it('retries an unknown submission with the same request id after reading the server', async () => {
    const requestIds: string[] = []
    let attemptCalls = 0
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(knowledgeBase)
      if (url.includes('/attempts') && init?.method === 'POST') {
        attemptCalls += 1
        requestIds.push(JSON.parse(String(init.body)).client_request_id)
        if (attemptCalls === 1) throw new TypeError('network down')
        return response(feedback('CORRECT'))
      }
      if (url.endsWith('/api/v1/learning-sessions/session-1')) {
        return response(attemptCalls > 1 ? session({ question: question(feedback('CORRECT')), completed_question_count: 1 }) : session())
      }
      return response({ status: 'ok', version: '0.1.0' })
    }))

    renderAt('/learning/session/session-1')
    fireEvent.click(await screen.findByRole('radio', { name: '30 秒' }))
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }))
    expect(await screen.findByText(/这次作答尚未保存/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }))
    expect(await screen.findByText('结果：正确')).toBeInTheDocument()
    expect(requestIds).toEqual([requestIds[0], requestIds[0]])
    expect(screen.getByText(/learning-demo-fixture-v1/)).toBeInTheDocument()
  })

  it('restores feedback after refresh and switches to another session', async () => {
    const saved = feedback('CORRECT')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(knowledgeBase)
      if (url.endsWith('/api/v1/learning-sessions/session-1')) return response(session({ question: question(saved), completed_question_count: 1 }))
      if (url.endsWith('/api/v1/learning-sessions/session-2')) {
        return response(session({
          learning_session_id: 'session-2',
          topic: '另一题',
          question: { ...question(), question_id: 'question-2', learning_session_id: 'session-2', prompt_text: '另一道未提交的题', feedback: null },
        }))
      }
      return response({ status: 'ok', version: '0.1.0' })
    }))

    const first = renderAt('/learning/session/session-1')
    expect(await screen.findByText('结果：正确')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '[1] 服务超时策略.txt' }))
    expect(await screen.findByRole('complementary', { name: '引用 1' })).toHaveTextContent('服务超时策略.txt')
    expect(screen.getByText(/持久任务不使用这个请求超时值/)).toBeInTheDocument()
    first.unmount()
    queryClient.clear()
    renderAt('/learning/session/session-1')
    expect(await screen.findByText('结果：正确')).toBeInTheDocument()
    window.history.pushState({}, '', '/learning/session/session-2')
    window.dispatchEvent(new PopStateEvent('popstate'))
    expect(await screen.findByText('另一道未提交的题')).toBeInTheDocument()
    expect(screen.queryByText('结果：正确')).not.toBeInTheDocument()
    expect(screen.queryByText(/持久任务不使用这个请求超时值/)).not.toBeInTheDocument()
  })

  it('shows insufficient evidence, source invalid, and model unavailable without a fake question', async () => {
    const cases = [
      {
        path: '/learning/session/insufficient',
        payload: session({
          learning_session_id: 'insufficient',
          status: 'FAILED',
          failure_code: 'EVIDENCE_INSUFFICIENT',
          failure_detail: '当前资料中没有找到足够的主题内容。',
          current_question_id: null,
          question: null,
        }),
        text: '当前资料中没有找到足够的主题内容。',
        action: '返回修改主题',
      },
      {
        path: '/learning/session/invalid',
        payload: session({
          learning_session_id: 'invalid',
          status: 'SOURCE_INVALID',
          failure_code: 'SOURCE_INVALID',
          failure_detail: '学习范围的资料已失效，不能继续作答，也不会改用普通聊天。',
          current_question_id: null,
          question: null,
        }),
        text: '也不会改用普通聊天',
        action: '返回知识库',
      },
      {
        path: '/learning/session/model',
        payload: session({
          learning_session_id: 'model',
          status: 'FAILED',
          failure_code: 'MODEL_UNAVAILABLE',
          failure_detail: '索引或检索当前不可用，不能出题，也不会改用普通聊天。',
          current_question_id: null,
          question: null,
        }),
        text: '索引或检索当前不可用',
        action: '返回知识库',
      },
    ]
    for (const item of cases) {
      queryClient.clear()
      vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/system/session')) return response({ status: 'ready' })
        if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(knowledgeBase)
        if (url.includes('/api/v1/learning-sessions/')) return response(item.payload)
        return response({ status: 'ok', version: '0.1.0' })
      }))
      const view = renderAt(item.path)
      expect(await screen.findByText(new RegExp(item.text))).toBeInTheDocument()
      expect(screen.getAllByRole('link', { name: item.action }).length).toBeGreaterThan(0)
      expect(screen.queryByRole('radio')).not.toBeInTheDocument()
      expect(screen.queryByText('answer_key')).not.toBeInTheDocument()
      expect(window.location.pathname).not.toBe('/chat')
      view.unmount()
    }
  })
})
