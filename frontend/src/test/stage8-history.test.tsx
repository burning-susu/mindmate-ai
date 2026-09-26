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
