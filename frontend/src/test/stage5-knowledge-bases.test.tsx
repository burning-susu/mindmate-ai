import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import App from '../App'

const baseItem = {
  knowledge_base_id: 'kb-1',
  name: '机器学习',
  description: '课程资料',
  icon: 'book-open',
  color: '#176b87',
  status: 'EMPTY',
  file_count: 0,
  available_file_count: 0,
  duplicate_name: false,
  created_at: '2026-09-23T00:00:00Z',
  updated_at: '2026-09-23T00:00:00Z',
  deleted_at: null,
  purge_after: null,
  row_version: 3,
}

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  })
}

describe('stage 5 knowledge base foundation', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders persisted knowledge bases and navigates to detail', async () => {
    window.history.pushState({}, '', '/knowledge-bases')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/knowledge-bases')) return response({ items: [baseItem], next_cursor: null })
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)

    expect(await screen.findByRole('heading', { name: '知识库' })).toBeInTheDocument()
    expect(await screen.findByText('机器学习')).toBeInTheDocument()
    expect(screen.getByText('空知识库')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /新建知识库/ })).toHaveAttribute('href', '/knowledge-bases/new')
  })

  it('creates an empty knowledge base through the real form contract', async () => {
    window.history.pushState({}, '', '/knowledge-bases/new')
    let createBody: Record<string, unknown> | undefined
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/knowledge-bases') && init?.method === 'POST') {
        createBody = JSON.parse(String(init.body)) as Record<string, unknown>
        return response({ ...baseItem, name: createBody.name, description: createBody.description }, 201)
      }
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(baseItem)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.change(await screen.findByRole('textbox', { name: '知识库名称' }), { target: { value: '操作系统' } })
    fireEvent.change(screen.getByRole('textbox', { name: '知识库描述' }), { target: { value: '考试复习' } })
    fireEvent.click(screen.getByRole('button', { name: '创建知识库' }))

    await waitFor(() => expect(createBody).toMatchObject({ name: '操作系统', description: '考试复习', icon: 'book-open' }))
  })

  it('sends row_version when editing and exposes the unavailable indexing state', async () => {
    window.history.pushState({}, '', '/knowledge-bases/kb-1')
    let patchBody: Record<string, unknown> | undefined
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1') && init?.method === 'PATCH') {
        patchBody = JSON.parse(String(init.body)) as Record<string, unknown>
        return response({ ...baseItem, ...patchBody, row_version: 4 })
      }
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(baseItem)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('添加文件与持久索引任务将在下一批开放。')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: '知识库描述' }), { target: { value: '新说明' } })
    fireEvent.click(screen.getByRole('button', { name: '保存更改' }))

    await waitFor(() => expect(patchBody).toMatchObject({ description: '新说明', row_version: 3 }))
  })

  it('loads knowledge bases in trash and restores with the persisted version', async () => {
    window.history.pushState({}, '', '/trash')
    let restoreUrl = ''
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/trash')) return response({ files: [], folders: [] })
      if (url.endsWith('/api/v1/trash/knowledge-bases')) return response({ items: [{ ...baseItem, status: 'IN_TRASH', deleted_at: '2026-09-23T00:00:00Z' }], next_cursor: null })
      if (url.includes('/api/v1/trash/knowledge-base/kb-1/restore') && init?.method === 'POST') {
        restoreUrl = url
        return response(baseItem)
      }
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: '恢复知识库' }))
    await waitFor(() => expect(restoreUrl).toContain('expected_version=3'))
  })
})
