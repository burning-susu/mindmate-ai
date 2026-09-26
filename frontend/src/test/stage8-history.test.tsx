import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import { clearLocalSessionCache } from '../api/client'
import App from '../App'
import { queryClient } from '../queryClient'

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  })
}

const provider = {
  provider: 'mock',
  display_name: 'Mock',
  configured: false,
  credential_store: { available: false, backend: 'memory' },
  requested_model: 'mock-chat-v1',
  consent: { accepted: false, version: null, accepted_at: null },
  probe: null,
  source_url: 'https://example.invalid',
  pricing_url: 'https://example.invalid',
  generation_mode: 'mock',
}

const historyItem = {
  conversation_id: 'conversation-1',
  title: '超时时间',
  summary: 'API 单次请求超时时间是多少秒？',
  current_mode: 'KNOWLEDGE_CHAT',
  scope_name: '服务超时演示库',
  status: 'SOURCE_INVALID',
  source_status: 'SOURCE_DELETED',
  message_count: 2,
  created_at: '2026-09-26T12:00:00Z',
  updated_at: '2026-09-26T12:05:00Z',
}

const savedMessages = {
  items: [
    {
      message_id: 'user-1',
      conversation_id: 'conversation-1',
      role: 'USER',
      content: 'API 单次请求超时时间是多少秒？',
      status: 'SENT',
      sequence_number: 1,
      request_id: null,
      mode_snapshot: 'KNOWLEDGE_CHAT',
      conversation_scope_id: null,
      parent_user_message_id: null,
      revision_number: 1,
      archived_at: null,
      created_at: '2026-09-26T12:00:00Z',
      updated_at: '2026-09-26T12:00:00Z',
      completed_at: null,
      citations: [],
    },
    {
      message_id: 'assistant-1',
      conversation_id: 'conversation-1',
      role: 'ASSISTANT',
      content: '资料结论 [1]',
      status: 'COMPLETED',
      sequence_number: 2,
      request_id: null,
      mode_snapshot: 'KNOWLEDGE_CHAT',
      conversation_scope_id: null,
      parent_user_message_id: 'user-1',
      revision_number: 1,
      archived_at: null,
      created_at: '2026-09-26T12:00:01Z',
      updated_at: '2026-09-26T12:00:01Z',
      completed_at: '2026-09-26T12:00:01Z',
      citations: [{
        citation_id: 'citation-1',
        answer_version_id: 'answer-1',
        source_snapshot_id: 'snapshot-1',
        display_number: 1,
        knowledge_base_id: 'kb-1',
        index_version_id: 'index-1',
        file_id: null,
        chunk_id: null,
        file_name: '服务超时策略.txt',
        file_version: null,
        heading_path: [],
        page_start: null,
        page_end: null,
        slide_number: null,
        line_start: 1,
        line_end: 12,
        excerpt: null,
        source_status: 'SOURCE_DELETED',
        can_open_source: false,
        created_at: '2026-09-26T12:00:01Z',
      }],
    },
  ],
}

afterEach(() => {
  vi.unstubAllGlobals()
  clearLocalSessionCache()
  queryClient.clear()
  window.history.pushState({}, '', '/')
})

describe('conversation history', () => {
  it('shows an empty history without creating a conversation', async () => {
    window.history.pushState({}, '', '/history')
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/conversations')) return response({ items: [], next_cursor: null })
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('还没有可阅读的对话。发送过的对话会保留在这里。')).toBeInTheDocument()
    expect(calls.some((call) => call.startsWith('POST') && call.includes('/conversations'))).toBe(false)
  })

  it('opens the original conversation and a deleted source without generating again', async () => {
    window.history.pushState({}, '', '/history')
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/conversations')) return response({ items: [historyItem], next_cursor: null })
      if (url.includes('/ai/provider')) return response(provider)
      if (url.endsWith('/conversations/conversation-1')) {
        return response({
          conversation_id: 'conversation-1',
          title: historyItem.title,
          title_source: 'AUTO',
          current_mode: 'KNOWLEDGE_CHAT',
          current_scope_type: 'KNOWLEDGE_BASE',
          current_scope_id_list: ['kb-1'],
          current_scope_name: '服务超时演示库',
          status: 'ACTIVE',
          message_count: 2,
          created_at: historyItem.created_at,
          updated_at: historyItem.updated_at,
          last_active_at: historyItem.updated_at,
          row_version: 2,
          active_operation_id: null,
        })
      }
      if (url.includes('/conversations/conversation-1/messages')) return response(savedMessages)
      if (url.endsWith('/conversations')) return response({ items: [], next_cursor: null })
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    const opener = await screen.findByRole('button', { name: /超时时间/ })
    fireEvent.click(opener)
    expect(await screen.findByText('API 单次请求超时时间是多少秒？')).toBeInTheDocument()
    expect(screen.getAllByText(/资料结论/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: '[1] 服务超时策略.txt' }))
    expect((await screen.findAllByText(/来源已永久删除/)).length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: /打开文件详情/ })).not.toBeInTheDocument()
    expect(calls.filter((call) => call.startsWith('POST') && call.includes('/conversations'))).toEqual([])
    expect(window.location.pathname).toBe('/chat/conversation-1')
  })

  it('keeps a readable failure state when history cannot load', async () => {
    window.history.pushState({}, '', '/history')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/conversations')) {
        return response({
          type: 'about:blank',
          title: '失败',
          status: 500,
          code: 'HISTORY_UNAVAILABLE',
          detail: '读取失败',
          instance: url,
          request_id: 'req-1',
        }, 500)
      }
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('对话历史暂时读不出来。')
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('还没有可阅读的对话。发送过的对话会保留在这里。')).not.toBeInTheDocument())
  })
})

const learningHistoryItem = {
  learning_session_id: 'learn-1',
  topic: '超时时间',
  goal_type: 'CUSTOM',
  scope_name: '服务超时演示库',
  scope_file_count: 1,
  status: 'IN_PROGRESS',
  source_status: 'AVAILABLE',
  answered_count: 0,
  target_question_count: 1,
  created_at: '2026-09-26T12:00:00Z',
  updated_at: '2026-09-26T12:05:00Z',
}

function learningSession(answered: boolean) {
  return {
    learning_session_id: 'learn-1',
    topic: '超时时间',
    goal_type: 'CUSTOM',
    goal_text: '记住请求超时上限',
    knowledge_base_id: 'kb-1',
    target_question_count: 1,
    status: answered ? 'IN_PROGRESS' : 'IN_PROGRESS',
    failure_code: null,
    failure_detail: null,
    completed_question_count: answered ? 1 : 0,
    current_question_id: 'question-1',
    provider: 'mock',
    model: 'learning-demo-fixture-v1',
    live_model_called: false,
    row_version: 2,
    created_at: learningHistoryItem.created_at,
    started_at: learningHistoryItem.created_at,
    scope: {
      knowledge_base_id: 'kb-1',
      index_version_id: 'index-1',
      source_set_hash: 'abc',
      file_ids: ['file-1'],
    },
    plan: null,
    question: {
      question_id: 'question-1',
      learning_session_id: 'learn-1',
      question_type: 'SINGLE_CHOICE',
      prompt_text: '普通请求的等待上限是多久？',
      options: [
        { option_id: 'opt-a', label: '30 秒' },
        { option_id: 'opt-b', label: '13 秒' },
      ],
      sequence_number: 1,
      status: answered ? 'ANSWERED' : 'OPEN',
      difficulty: 'BASIC',
      row_version: 1,
      feedback: answered ? {
        feedback_id: 'feedback-1',
        attempt_id: 'attempt-1',
        selected_option: 'opt-a',
        result: 'CORRECT',
        explanation: '与资料记载一致 [1]',
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
          excerpt: 'API 单次请求超时时间为 30 秒。',
          source_status: 'AVAILABLE',
          can_open_source: true,
        }],
      } : null,
    },
  }
}

describe('learning history', () => {
  it('opens an empty learning tab from the learning page without creating a session', async () => {
    window.history.pushState({}, '', '/learning')
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) return response({ items: [], next_cursor: null })
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('link', { name: '学习历史' }))
    expect(await screen.findByText('还没有可找回的学习会话。从知识库开始的一题会保留在这里。')).toBeInTheDocument()
    expect(calls.some((call) => call.startsWith('POST') && call.includes('/learning-sessions'))).toBe(false)
  })

  it('returns to an unanswered session without submitting', async () => {
    window.history.pushState({}, '', '/history?tab=learning')
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) return response({ items: [learningHistoryItem], next_cursor: null })
      if (url.includes('/learning-sessions/learn-1')) return response(learningSession(false))
      if (url.includes('/knowledge-bases/kb-1')) return response({ knowledge_base_id: 'kb-1', name: '服务超时演示库', status: 'READY', available_file_count: 1, file_count: 1, row_version: 1 })
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /超时时间/ }))
    expect(await screen.findByText('普通请求的等待上限是多久？')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '提交答案' })).toBeInTheDocument()
    expect(calls.filter((call) => call.startsWith('POST') && call.includes('/attempts'))).toEqual([])
    expect(window.location.pathname).toBe('/learning/session/learn-1')
  })

  it('returns to a submitted answer and its source without a new attempt', async () => {
    window.history.pushState({}, '', '/history?tab=learning')
    const calls: string[] = []
    const item = { ...learningHistoryItem, answered_count: 1 }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) return response({ items: [item], next_cursor: null })
      if (url.includes('/learning-sessions/learn-1')) return response(learningSession(true))
      if (url.includes('/knowledge-bases/kb-1')) return response({ knowledge_base_id: 'kb-1', name: '服务超时演示库', status: 'READY', available_file_count: 1, file_count: 1, row_version: 1 })
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /已作答 1 \/ 1/ }))
    expect(await screen.findByText('结果：正确')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '提交答案' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '[1] 服务超时策略.txt' }))
    expect(await screen.findByText(/API 单次请求超时时间为 30 秒/)).toBeInTheDocument()
    expect(calls.filter((call) => call.startsWith('POST') && call.includes('/attempts'))).toEqual([])
  })

  it('keeps a readable failure state when learning history cannot load', async () => {
    window.history.pushState({}, '', '/history?tab=learning')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) {
        return response({
          type: 'about:blank',
          title: '失败',
          status: 500,
          code: 'HISTORY_UNAVAILABLE',
          detail: '读取失败',
          instance: url,
          request_id: 'req-1',
        }, 500)
      }
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('学习历史暂时读不出来。')
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('还没有可找回的学习会话。从知识库开始的一题会保留在这里。')).not.toBeInTheDocument())
  })
})
