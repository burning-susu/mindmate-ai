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

function knowledgeBase(name: string, status: string, available = 0) {
  return {
    knowledge_base_id: `kb-${name}`,
    name,
    description: status === 'READY' ? '公开合成资料' : null,
    icon: null,
    color: null,
    status,
    file_count: available,
    available_file_count: available,
    duplicate_name: false,
    created_at: '2026-09-26T08:00:00Z',
    updated_at: '2026-09-26T09:00:00Z',
    deleted_at: null,
    purge_after: null,
    row_version: 1,
  }
}

function fileItem(name: string, status: string) {
  return {
    file_id: `file-${name}`,
    display_name: name,
    source_name: name,
    extension: '.txt',
    document_type: 'TXT',
    folder_id: null,
    folder_name: name === '失败资料.txt' ? '课程' : null,
    status,
    content_hash: 'hash',
    byte_size: 12,
    created_at: '2026-09-26T08:00:00Z',
    updated_at: '2026-09-26T09:30:00Z',
    deleted_at: null,
    purge_after: null,
    row_version: 1,
    tags: name === '失败资料.txt' ? [{ tag_id: 'tag-1', name: '超时', color: null, row_version: 1, created_at: '2026-09-26T08:00:00Z', updated_at: '2026-09-26T08:00:00Z' }] : [],
    parsed_metadata: null,
    has_parsed_text: status === 'PARSED',
    content_available: true,
    parse_failure_stage: status === 'PARSE_FAILED' ? 'PARSING' : null,
    parse_error_id: status === 'PARSE_FAILED' ? 'OCR_REQUIRED' : null,
    parse_retry_count: status === 'PARSE_FAILED' ? 1 : 0,
    can_reprocess: status === 'PARSE_FAILED',
  }
}

function conversation(title: string, sourceStatus: string) {
  return {
    conversation_id: `chat-${title}`,
    title,
    summary: '超时时间是多少',
    current_mode: sourceStatus === 'NOT_APPLICABLE' ? 'GENERAL_CHAT' : 'KNOWLEDGE_CHAT',
    scope_name: sourceStatus === 'NOT_APPLICABLE' ? null : '服务超时演示库',
    status: sourceStatus === 'AVAILABLE' || sourceStatus === 'NOT_APPLICABLE' ? 'ACTIVE' : 'SOURCE_INVALID',
    source_status: sourceStatus,
    message_count: 2,
    created_at: '2026-09-26T08:00:00Z',
    updated_at: '2026-09-26T10:00:00Z',
  }
}

const emptyHomeOverview = {
  files: 0,
  knowledge_bases: 0,
  conversations: 0,
  learning_sessions: 0,
  count_scope: {
    files: '未回收文件，包含解析失败和其他未进回收站的状态',
    knowledge_bases: '未回收知识库，包含空库、准备中和索引失败',
    conversations: '未回收对话，包含普通对话和知识库对话',
    learning_sessions: '未回收学习会话，包含未完成、已完成和未能出题',
  },
  tasks: {
    queued_count: 0,
    running_count: 0,
    failed_count: 0,
    blocked_count: 0,
    interrupted_count: 0,
    total_count: 0,
    latest: null,
    recent: [],
  },
}

afterEach(() => {
  vi.unstubAllGlobals()
  clearLocalSessionCache()
  queryClient.clear()
  window.history.pushState({}, '', '/')
})

describe('home recent content', () => {
  it('shows empty sections and does not create records', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/home/overview')) return response(emptyHomeOverview)
      if (url.includes('/history/learning-sessions')) return response({ items: [], next_cursor: null })
      if (url.includes('/history/conversations')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/knowledge-bases')) return response({ items: [], next_cursor: null })
      if (url.includes('/api/v1/files')) return response({ items: [], next_cursor: null, limit: 5 })
      return response({ status: 'ok' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('还没有未回收的知识库。')).toBeInTheDocument()
    expect(screen.getByText('还没有未回收的文件。')).toBeInTheDocument()
    expect(screen.getByText('还没有未回收的对话。')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '开始第一次学习' })).toBeInTheDocument()
    const knowledge = screen.getByRole('region', { name: '最近知识库' })
    const files = screen.getByRole('region', { name: '最近文件' })
    const conversations = screen.getByRole('region', { name: '最近对话' })
    expect(within(knowledge).getByRole('link', { name: '查看全部' })).toHaveAttribute('href', '/knowledge-bases')
    expect(within(files).getByRole('link', { name: '查看全部' })).toHaveAttribute('href', '/files')
    expect(within(conversations).getByRole('link', { name: '查看全部' })).toHaveAttribute('href', '/history')
    expect(calls.some((call) => call.includes('/knowledge-bases?limit=4'))).toBe(true)
    expect(calls.some((call) => call.includes('/files?limit=5&sort=updated_at'))).toBe(true)
    expect(calls.some((call) => call.includes('/history/conversations?limit=5'))).toBe(true)
    expect(calls.filter((call) => call.startsWith('POST') && !call.includes('/system/session'))).toEqual([])
  })

  it('caps each column and keeps ready actions behind the existing gates', async () => {
    const calls: string[] = []
    const bases = ['一', '二', '三', '四', '五'].map((name, index) => ({
      ...knowledgeBase(name, index === 0 ? 'READY' : 'FAILED', index === 0 ? 2 : 0),
      description: index === 3 ? '' : '简述',
    }))
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/home/overview')) return response(emptyHomeOverview)
      if (url.includes('/history/learning-sessions')) return response({ items: [], next_cursor: null })
      if (url.includes('/history/conversations')) {
        return response({
          items: [
            conversation('普通问答', 'NOT_APPLICABLE'),
            conversation('带来源问答', 'SOURCE_IN_TRASH'),
          ],
          next_cursor: null,
        })
      }
      if (url.includes('/api/v1/knowledge-bases')) return response({ items: bases, next_cursor: null })
      if (url.includes('/api/v1/files') && init?.method === 'POST') return response({ task_id: 'retry-1' })
      if (url.includes('/api/v1/files')) {
        return response({
          items: [fileItem('服务超时策略.txt', 'PARSED'), fileItem('失败资料.txt', 'PARSE_FAILED')],
          next_cursor: null,
          limit: 5,
        })
      }
      return response({ status: 'ok' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    const knowledge = await screen.findByRole('region', { name: '最近知识库' })
    expect(await within(knowledge).findByRole('link', { name: '一' })).toHaveAttribute('href', '/knowledge-bases/kb-一')
    expect(within(knowledge).getByText('2 个文件')).toBeInTheDocument()
    expect(within(knowledge).getByText('索引就绪')).toBeInTheDocument()
    expect(within(knowledge).getAllByText('索引失败').length).toBeGreaterThan(0)
    expect(within(knowledge).getAllByText('最近更新').length).toBeGreaterThan(0)
    expect(within(knowledge).queryByText('五')).not.toBeInTheDocument()
    expect(within(knowledge).queryByText('undefined')).not.toBeInTheDocument()
    const readyCard = within(knowledge).getByRole('heading', { name: '一' }).closest('article') as HTMLElement
    expect(within(readyCard).getByRole('link', { name: '开始学习' })).toHaveAttribute('href', '/learning/new?knowledge_base_id=kb-%E4%B8%80')
    expect(within(readyCard).getByRole('link', { name: '提问' })).toHaveAttribute('href', '/chat?knowledge_base_id=kb-%E4%B8%80')
    const failedCard = within(knowledge).getByRole('heading', { name: '二' }).closest('article') as HTMLElement
    expect(within(failedCard).queryByRole('link', { name: '开始学习' })).not.toBeInTheDocument()
    expect(within(failedCard).getByRole('link', { name: '查看知识库' })).toHaveAttribute('href', '/knowledge-bases/kb-二')

    const files = screen.getByRole('region', { name: '最近文件' })
    expect(within(files).getByText('已解析')).toBeInTheDocument()
    expect(within(files).getByText('解析失败 · 阶段 PARSING · 错误 OCR_REQUIRED')).toBeInTheDocument()
    expect(within(files).getByText('课程')).toBeInTheDocument()
    expect(within(files).getByText('超时')).toBeInTheDocument()
    expect(within(files).getByText('未分类')).toBeInTheDocument()
    const failedFile = within(files).getByRole('heading', { name: '失败资料.txt' }).closest('article') as HTMLElement
    fireEvent.click(within(failedFile).getByRole('button', { name: '重试处理' }))
    expect(calls.some((call) => call.includes('/reprocess'))).toBe(false)
    fireEvent.click(within(failedFile).getByRole('button', { name: '确认重试' }))
    await waitFor(() => expect(calls.some((call) => call.startsWith('POST') && call.includes('/reprocess'))).toBe(true))

    const conversations = screen.getByRole('region', { name: '最近对话' })
    expect(within(conversations).getByText('普通对话')).toBeInTheDocument()
    expect(within(conversations).getByText('服务超时演示库')).toBeInTheDocument()
    expect(within(conversations).getByText(/文件已在回收站/)).toBeInTheDocument()
    expect(within(conversations).getAllByRole('link', { name: '查看对话' })[1]).toHaveAttribute('href', '/chat/chat-带来源问答')
    expect(screen.queryByText('undefined')).not.toBeInTheDocument()
  })

  it('keeps the other columns when one read fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.includes('/home/overview')) return response(emptyHomeOverview)
      if (url.includes('/history/learning-sessions')) return response({ items: [], next_cursor: null })
      if (url.includes('/history/conversations')) return response({ title: '读取失败' }, 503)
      if (url.includes('/api/v1/knowledge-bases')) return response({ items: [knowledgeBase('仍在', 'EMPTY')], next_cursor: null })
      if (url.includes('/api/v1/files')) return response({ items: [fileItem('服务超时策略.txt', 'PARSED')], next_cursor: null, limit: 5 })
      return response({ status: 'ok' })
    }))
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('link', { name: '仍在' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '服务超时策略.txt' })).toBeInTheDocument()
    expect(screen.getByText('最近对话暂时读不出来。')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '继续学习' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '快捷操作' })).toBeInTheDocument()
  })
})
