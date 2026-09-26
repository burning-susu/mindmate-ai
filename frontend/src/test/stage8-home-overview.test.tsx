import { fireEvent, render, screen, within } from '@testing-library/react'
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
  files: '未回收文件，包含解析失败和其他未进回收站的状态',
  knowledge_bases: '未回收知识库，包含空库、准备中和索引失败',
  conversations: '未回收对话，包含普通对话和知识库对话',
  learning_sessions: '未回收学习会话，包含未完成、已完成和未能出题',
}

function overview(tasks = {}, counts: Record<string, number> = {}) {
  return {
    files: 0,
    knowledge_bases: 0,
    conversations: 0,
    learning_sessions: 0,
    ...counts,
    count_scope: scope,
    tasks: {
      queued_count: 0,
      running_count: 0,
      failed_count: 0,
      blocked_count: 0,
      interrupted_count: 0,
      total_count: 0,
      latest: null,
      recent: [],
      ...tasks,
    },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  clearLocalSessionCache()
  queryClient.clear()
  window.history.pushState({}, '', '/')
})

describe('home overview and task panel', () => {
  it('shows zero counts and a collapsed task entry without writing', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/home/overview')) return response(overview())
      if (url.includes('/history/learning-sessions')) return response({ items: [], next_cursor: null })
      if (url.includes('/history/conversations')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/knowledge-bases')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/files')) return response({ items: [], next_cursor: null })
      return response({ status: 'ok' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    const fileCount = await screen.findByRole('link', { name: /未回收文件/ })
    expect(fileCount).toHaveAttribute('href', '/files')
    expect(fileCount).toHaveTextContent('0')
    expect(screen.getByRole('link', { name: /未回收知识库/ })).toHaveAttribute('href', '/knowledge-bases')
    expect(screen.getByRole('link', { name: /未回收对话/ })).toHaveAttribute('href', '/history')
    expect(screen.getByRole('link', { name: /未回收学习会话/ })).toHaveAttribute('href', '/history?tab=learning')
    expect(screen.queryByRole('heading', { name: '任务状态' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看后台任务' }))
    const panel = await screen.findByRole('dialog', { name: '后台任务' })
    expect(within(panel).getByText('当前没有后台任务。')).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: '取消' })).not.toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
    expect(calls.filter((call) => call.startsWith('POST') && !call.includes('/system/session'))).toEqual([])
    expect(calls.some((call) => call.includes('/api/v1/tasks/'))).toBe(false)
  })

  it('keeps recent content when the overview request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/home/overview')) return response({ title: '读取失败' }, 503)
      if (url.includes('/history/learning-sessions')) return response({ items: [], next_cursor: null })
      if (url.includes('/history/conversations')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/knowledge-bases')) return response({ items: [{ knowledge_base_id: 'kb-1', name: '仍在的库', description: null, status: 'EMPTY', file_count: 0, available_file_count: 0, updated_at: '2026-09-26T08:00:00Z' }], next_cursor: null })
      if (url.includes('/api/v1/files')) return response({ items: [], next_cursor: null })
      return response({ status: 'ok' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('link', { name: '仍在的库' })).toBeInTheDocument()
    expect(screen.getByText('概览暂时读不出来，不能把失败显示成 0。')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /未回收文件/ })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '继续学习' })).toBeInTheDocument()
  })

  it('shows real task states in a read-only panel and stops observing after unmount', async () => {
    const calls: string[] = []
    const running = {
      task_id: 'task-running',
      task_type: 'INDEX_CHUNK',
      status: 'RUNNING',
      phase: 'CHUNKING',
      progress_percent: null,
      failure_code: null,
      failure_summary: null,
      updated_at: '2026-09-26T09:04:00Z',
    }
    const failed = {
      task_id: 'task-failed',
      task_type: 'FILE_REPROCESS',
      status: 'FAILED',
      phase: 'PARSING',
      progress_percent: null,
      failure_code: 'PARSER_FAILED',
      failure_summary: '失败详情已省略',
      updated_at: '2026-09-26T09:06:00Z',
    }
    const measured = {
      task_id: 'task-embed',
      task_type: 'INDEX_EMBED',
      status: 'RUNNING',
      phase: 'EMBEDDING',
      progress_percent: 40,
      failure_code: null,
      failure_summary: null,
      updated_at: '2026-09-26T09:05:00Z',
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/home/overview')) {
        return response(overview({
          queued_count: 1,
          running_count: 2,
          failed_count: 1,
          total_count: 4,
          latest: failed,
          recent: [failed, measured, running],
        }))
      }
      if (url.includes('/history/')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/knowledge-bases')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/files')) return response({ items: [], next_cursor: null })
      return response({ status: 'ok' })
    }))
    const view = render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('heading', { name: '任务状态' })).toBeInTheDocument()
    expect(screen.getByText('排队').nextElementSibling).toHaveTextContent('1')
    expect(screen.getByText(/最近一条：重新处理文件 · 失败 · PARSING · PARSER_FAILED · 失败详情已省略/)).toBeInTheDocument()
    expect(screen.queryByText('sk-live-secret')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看全部任务' }))
    const panel = await screen.findByRole('dialog', { name: '后台任务' })
    expect(within(panel).getByText(/索引切块 · 运行中 · CHUNKING/)).toBeInTheDocument()
    expect(within(panel).getByText(/索引向量 · 运行中 · 40%/)).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: '取消' })).not.toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: '重试' })).not.toBeInTheDocument()
    fireEvent.click(within(panel).getAllByRole('button', { name: '查看详情' })[1])
    expect(within(panel).getAllByText('40%').length).toBeGreaterThan(0)
    expect(calls.some((call) => call.includes('/api/v1/tasks/'))).toBe(false)
    expect(calls.filter((call) => call.startsWith('POST') && !call.includes('/system/session'))).toEqual([])
    view.unmount()
    expect(queryClient.getQueryCache().findAll({ queryKey: ['home-overview'] }).every((query) => query.getObserversCount() === 0)).toBe(true)
  })
})
