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

const recent = {
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

function learningCalls(calls: string[]): string[] {
  return calls.filter((call) => call.startsWith('POST') && (call.includes('/learning-sessions') || call.includes('/attempts') || call.includes('/current-question')))
}

afterEach(() => {
  vi.unstubAllGlobals()
  clearLocalSessionCache()
  queryClient.clear()
  window.history.pushState({}, '', '/')
})

describe('home continue learning', () => {
  it('shows the first-learning guidance without creating a session', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) return response({ items: [], next_cursor: null })
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('link', { name: '开始第一次学习' })).toHaveAttribute('href', '/knowledge-bases')
    expect(screen.getByRole('link', { name: '先导入资料' })).toHaveAttribute('href', '/files')
    expect(screen.getByText(/索引就绪、并且有可用文件/)).toBeInTheDocument()
    expect(calls.some((call) => call.includes('/history/learning-sessions?limit=1'))).toBe(true)
    expect(learningCalls(calls)).toEqual([])
  })

  it('links an unanswered session to the original url without submitting', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) return response({ items: [recent], next_cursor: null })
      if (url.includes('/learning-sessions/learn-1')) {
        return response({
          learning_session_id: 'learn-1',
          topic: '超时时间',
          goal_text: '记住请求超时上限',
          knowledge_base_id: 'kb-1',
          target_question_count: 1,
          status: 'IN_PROGRESS',
          completed_question_count: 0,
          provider: 'mock',
          model: 'learning-demo-fixture-v1',
          live_model_called: false,
          scope: { file_ids: ['file-1'] },
          question: {
            question_id: 'question-1',
            sequence_number: 1,
            prompt_text: '普通请求的等待上限是多久？',
            options: [{ option_id: 'opt-a', label: '30 秒' }],
            status: 'OPEN',
            feedback: null,
          },
        })
      }
      if (url.includes('/knowledge-bases/kb-1')) return response({ knowledge_base_id: 'kb-1', name: '服务超时演示库', status: 'READY', available_file_count: 1, file_count: 1, row_version: 1 })
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('未作答')).toBeInTheDocument()
    expect(screen.getByText('服务超时演示库 · 1 个文件')).toBeInTheDocument()
    expect(screen.getByText('0 / 1')).toBeInTheDocument()
    expect(screen.getByText('已作答数量')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: '继续学习' })
    expect(link).toHaveAttribute('href', '/learning/session/learn-1')
    expect(screen.queryByRole('link', { name: '查看总结' })).not.toBeInTheDocument()
    fireEvent.click(link)
    expect(await screen.findByRole('button', { name: '提交答案' })).toBeInTheDocument()
    expect(learningCalls(calls)).toEqual([])
  })

  it('opens saved feedback and does not offer a summary', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) return response({ items: [{ ...recent, answered_count: 1 }], next_cursor: null })
      if (url.includes('/learning-sessions/learn-1')) {
        return response({
          learning_session_id: 'learn-1',
          topic: '超时时间',
          goal_text: '记住请求超时上限',
          knowledge_base_id: 'kb-1',
          target_question_count: 1,
          status: 'IN_PROGRESS',
          completed_question_count: 1,
          provider: 'mock',
          model: 'learning-demo-fixture-v1',
          live_model_called: false,
          scope: { file_ids: ['file-1'] },
          question: {
            question_id: 'question-1',
            sequence_number: 1,
            prompt_text: '普通请求的等待上限是多久？',
            options: [{ option_id: 'opt-a', label: '30 秒' }],
            status: 'ANSWERED',
            feedback: {
              feedback_id: 'feedback-1',
              attempt_id: 'attempt-1',
              selected_option: 'opt-a',
              result: 'CORRECT',
              explanation: '与资料记载一致',
              provider: 'mock',
              model: 'learning-demo-fixture-v1',
              live_model_called: false,
              citations: [],
            },
          },
        })
      }
      if (url.includes('/knowledge-bases/kb-1')) return response({ knowledge_base_id: 'kb-1', name: '服务超时演示库', status: 'READY', available_file_count: 1, file_count: 1, row_version: 1 })
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('已作答')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '继续学习' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '查看总结' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '查看反馈' }))
    expect(await screen.findByText('结果：正确')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '提交答案' })).not.toBeInTheDocument()
    expect(learningCalls(calls)).toEqual([])
  })

  it('blocks continue when the source is invalid and keeps the reason', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) {
        return response({
          items: [{ ...recent, status: 'SOURCE_INVALID', source_status: 'SOURCE_IN_TRASH' }],
          next_cursor: null,
        })
      }
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText(/文件已在回收站/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '继续学习' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '查看原会话' })).toHaveAttribute('href', '/learning/session/learn-1')
    expect(screen.getByRole('link', { name: '学习历史' })).toHaveAttribute('href', '/history?tab=learning')
    expect(learningCalls(calls)).toEqual([])
  })

  it('hides a previously loaded card when the latest read fails', async () => {
    let fail = false
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/history/learning-sessions')) {
        if (fail) {
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
        return response({ items: [recent], next_cursor: null })
      }
      return response({ status: 'ok', version: '0.1.0' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('link', { name: '继续学习' })).toBeInTheDocument()
    fail = true
    fireEvent.click(screen.getByRole('link', { name: '学习历史' }))
    window.history.pushState({}, '', '/')
    fireEvent.click(screen.getByRole('link', { name: '首页' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('最近学习暂时读不出来'))
    expect(screen.queryByRole('link', { name: '继续学习' })).not.toBeInTheDocument()
    expect(screen.queryByText('超时时间')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '打开学习历史' })).toHaveAttribute('href', '/history?tab=learning')
  })
})
