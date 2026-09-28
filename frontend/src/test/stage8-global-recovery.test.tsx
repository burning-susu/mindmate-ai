import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

const scope = {
  files: '未回收文件',
  knowledge_bases: '未回收知识库',
  conversations: '未回收对话',
  learning_sessions: '未回收学习会话',
}

function overview(task: Record<string, unknown>) {
  return {
    files: 0,
    knowledge_bases: 0,
    conversations: 0,
    learning_sessions: 0,
    count_scope: scope,
    tasks: {
      queued_count: task.status === 'QUEUED' ? 1 : 0,
      running_count: task.status === 'RUNNING' ? 1 : 0,
      failed_count: task.status === 'FAILED' ? 1 : 0,
      blocked_count: task.status === 'BLOCKED' ? 1 : 0,
      interrupted_count: 0,
      total_count: 1,
      latest: task,
      recent: [task],
    },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  clearLocalSessionCache()
  queryClient.clear()
  Object.defineProperty(window.navigator, 'onLine', { configurable: true, value: true })
  window.history.pushState({}, '', '/')
})

describe('stage 8 global recovery', () => {
  it('keeps a persisted task visible outside home and cancels it once through the supported API', async () => {
    let cancelled = false
    const calls: Array<{ url: string; method: string }> = []
    const task = {
      task_id: 'import-task-1',
      task_type: 'FILE_IMPORT',
      status: 'QUEUED',
      phase: 'PARSING',
      progress_percent: 20,
      failure_code: null,
      failure_summary: null,
      updated_at: '2026-09-28T12:00:00Z',
    }
    window.history.pushState({}, '', '/files')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ url, method })
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/api/v1/health')) return response({ status: 'ok', version: '0.1.0' })
      if (url.includes('/home/overview')) return response(overview({ ...task, status: cancelled ? 'CANCELLED' : 'QUEUED', phase: cancelled ? 'CANCELLED' : task.phase, progress_percent: cancelled ? null : task.progress_percent }))
      if (url.includes('/api/v1/files')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/folders')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/tags')) return response({ items: [], next_cursor: null })
      if (url.endsWith('/file-imports/import-task-1/cancel') && method === 'POST') {
        cancelled = true
        return response({ task_id: 'import-task-1', status: 'CANCELLED' })
      }
      return response({ status: 'ok' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    const trigger = await screen.findByRole('button', { name: /打开全局任务/ })
    fireEvent.click(trigger)
    const drawer = await screen.findByRole('dialog', { name: '后台任务' })
    expect(within(drawer).getByText('导入文件')).toBeInTheDocument()
    expect(within(drawer).getByText('阶段：PARSING · 进度：20%')).toBeInTheDocument()
    expect(within(drawer).getByRole('button', { name: '取消任务' })).toBeInTheDocument()

    fireEvent.click(within(drawer).getByRole('button', { name: '取消任务' }))
    await waitFor(() => expect(calls.filter((call) => call.method === 'POST' && call.url.endsWith('/file-imports/import-task-1/cancel'))).toHaveLength(1))
    await waitFor(() => expect(within(drawer).getAllByText('已取消').length).toBeGreaterThan(0))
    expect(calls.filter((call) => call.method === 'POST' && call.url.endsWith('/file-imports/import-task-1/cancel'))).toHaveLength(1)
  })

  it('shows a blocking local service state when the loopback API cannot connect', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('heading', { name: '本地服务不可用' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重新连接' })).toBeInTheDocument()
    expect(screen.getByText(/无法读取本地文件、知识库、历史和后台任务/)).toBeInTheDocument()
  })

  it('blocks an online provider submission while the loopback API remains usable offline', async () => {
    Object.defineProperty(window.navigator, 'onLine', { configurable: true, value: false })
    const calls: Array<{ url: string; method: string }> = []
    window.history.pushState({}, '', '/chat')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ url, method })
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/api/v1/health')) return response({ status: 'ok', version: '0.1.0' })
      if (url.includes('/home/overview')) return response(overview({ task_id: 'offline-task', task_type: 'CHAT_GENERATION', status: 'COMPLETED', phase: 'COMPLETED', progress_percent: 100, failure_code: null, failure_summary: null, updated_at: '2026-09-28T12:00:00Z' }))
      if (url.endsWith('/api/v1/ai/provider')) {
        return response({
          generation_mode: 'deepseek',
          configured: true,
          requested_model: 'deepseek-flash',
          consent: { accepted: true, current_version: 'v1', version: 'v1', accepted_at: '2026-09-28T00:00:00Z' },
          credential_store: { available: true, type: 'test', error_code: null },
          cost_estimate: { disclaimer: '本地估算。', knowledge_question_estimated_usd_ceiling: '0.01' },
        })
      }
      if (url.includes('/api/v1/chat/conversations')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/knowledge-bases')) return response({ items: [], next_cursor: null })
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    const composer = await screen.findByRole('textbox', { name: '消息内容' })
    fireEvent.change(composer, { target: { value: '离线时不要外发' } })
    expect(await screen.findByRole('alert')).toHaveTextContent('当前设备处于离线状态')
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
    expect(calls.filter((call) => call.method === 'POST' && !call.url.includes('/system/session'))).toEqual([])
  })
})
