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

const readyBase = {
  knowledge_base_id: 'kb-ready',
  name: '服务超时演示库',
  description: '公开合成资料',
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

function mutatingCalls(calls: string[]): string[] {
  return calls.filter((call) => /^(POST|PUT|PATCH|DELETE) /.test(call) && !call.includes('/system/session'))
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

function installFetch(options: { knowledgeBases?: unknown[]; failKnowledgeBases?: boolean } = {}) {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method ?? 'GET'} ${url}`)
    if (url.includes('/system/session')) return response({ status: 'ready' })
    if (url.includes('/home/overview')) return response(emptyHomeOverview)
    if (url.includes('/history/learning-sessions')) return response({ items: [], next_cursor: null })
    if (url.includes('/api/v1/knowledge-bases') && url.includes('/files')) return response({ items: [] })
    if (url.includes('/api/v1/knowledge-bases')) {
      if (options.failKnowledgeBases) return response({ title: '读取失败', detail: '知识库列表暂时不可用' }, 503)
      if (url.endsWith('/kb-ready')) return response(readyBase)
      return response({ items: options.knowledgeBases ?? [], next_cursor: null })
    }
    if (url.includes('/api/v1/files')) return response({ items: [], next_cursor: null })
    if (url.includes('/api/v1/folders')) return response({ items: [] })
    if (url.includes('/api/v1/tags')) return response({ items: [] })
    if (url.includes('/conversations')) return response({ items: [], next_cursor: null })
    if (url.includes('/ai/provider')) return response({ generation_mode: 'mock', configured: false, consent: { accepted: false }, credential_store: { available: false } })
    return response({ status: 'ok', version: '0.1.0' })
  }))
  return calls
}

describe('home shortcuts', () => {
  it('keeps four entries on an empty library and does not create records', async () => {
    const calls = installFetch()
    render(<BrowserRouter><App /></BrowserRouter>)

    const start = await screen.findByRole('link', { name: '开始学习' })
    expect(start).toHaveAttribute('href', '/learning/new')
    expect(screen.getByRole('link', { name: 'AI 提问' })).toHaveAttribute('href', '/chat')
    expect(screen.getByRole('link', { name: '导入文件' })).toHaveAttribute('href', '/files')
    expect(screen.getByRole('link', { name: '创建知识库' })).toHaveAttribute('href', '/knowledge-bases/new')
    expect(screen.getByRole('heading', { name: '继续学习' })).toBeInTheDocument()

    fireEvent.click(start)
    expect(await screen.findByRole('heading', { name: '选择知识库' })).toBeInTheDocument()
    expect(await screen.findByText(/还没有索引就绪、并且有可用文件的知识库/)).toBeInTheDocument()
    const learningChoices = screen.getByRole('heading', { name: '选择知识库' }).closest('div')
    expect(learningChoices).not.toBeNull()
    expect(within(learningChoices as HTMLElement).getByRole('link', { name: '导入文件' })).toHaveAttribute('href', '/files')
    expect(within(learningChoices as HTMLElement).getByRole('link', { name: '知识库' })).toHaveAttribute('href', '/knowledge-bases')
    fireEvent.click(screen.getByRole('link', { name: '首页' }))

    fireEvent.click(await screen.findByRole('link', { name: 'AI 提问' }))
    expect(await screen.findByRole('heading', { name: '普通聊天' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '普通对话' })).toHaveAttribute('href', '/chat')
    expect(await screen.findByText(/还没有索引就绪的知识库/)).toBeInTheDocument()
    expect(screen.getByText(/不会建立知识库会话/)).toBeInTheDocument()
    expect(screen.getByText(/Mock 生成/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '首页' }))

    fireEvent.click(await screen.findByRole('link', { name: '导入文件' }))
    expect(await screen.findByRole('heading', { name: '文件' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '导入文件' }).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('link', { name: '首页' }))

    fireEvent.click(await screen.findByRole('link', { name: '创建知识库' }))
    expect(await screen.findByRole('heading', { name: '新建知识库' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '知识库名称' })).toHaveValue('')
    expect(screen.getByRole('button', { name: '创建知识库' })).toBeDisabled()
    fireEvent.click(screen.getByRole('link', { name: '首页' }))
    expect(await screen.findByRole('heading', { name: '快捷操作' })).toBeInTheDocument()
    expect(mutatingCalls(calls)).toEqual([])
  })

  it('opens a ready knowledge base for learning and chat without sending', async () => {
    const calls = installFetch({ knowledgeBases: [readyBase] })
    render(<BrowserRouter><App /></BrowserRouter>)

    const shortcuts = await screen.findByRole('region', { name: '快捷操作' })
    fireEvent.click(within(shortcuts).getByRole('link', { name: '开始学习' }))
    const learningChoice = await screen.findByRole('link', { name: '服务超时演示库' })
    expect(learningChoice).toHaveAttribute('href', '/learning/new?knowledge_base_id=kb-ready')
    fireEvent.click(learningChoice)
    expect(await screen.findByRole('button', { name: '创建并开始' })).toBeDisabled()
    expect(screen.getByText(/打开本页不会创建学习会话/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '首页' }))

    fireEvent.click(await screen.findByRole('link', { name: 'AI 提问' }))
    const chatChoice = await screen.findByRole('link', { name: '服务超时演示库' })
    expect(chatChoice).toHaveAttribute('href', '/chat?knowledge_base_id=kb-ready')
    fireEvent.click(chatChoice)
    expect(await screen.findByRole('heading', { name: '知识库问答' })).toBeInTheDocument()
    expect(await screen.findByText(/当前范围：服务超时演示库/)).toBeInTheDocument()
    expect(screen.queryByText(/不会建立知识库会话/)).not.toBeInTheDocument()
    await waitFor(() => expect(mutatingCalls(calls)).toEqual([]))
  })

  it('shows a real list error instead of an empty shortcut target', async () => {
    installFetch({ failKnowledgeBases: true })
    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('link', { name: '开始学习' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('知识库列表暂时不可用')
    expect(screen.queryByText('undefined')).not.toBeInTheDocument()
  })
})
