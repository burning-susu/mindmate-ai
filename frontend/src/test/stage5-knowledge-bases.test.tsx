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

type MockIndexStatus = {
  knowledge_base_id: string
  status: string
  active_index_version_id: string | null
  active_index_version_status: string | null
  target_index_version_id: string | null
  target_index_version_status: string | null
  target_stage: string | null
  file_counts: { total: number; available: number; processing: number; failed: number }
  failures: Array<{ file_id: string; display_name: string; stage: string; reason_code: string; message: string; retryable: boolean; diagnostic_id: string | null }>
  tasks: Array<{ task_id: string; task_type: string; status: string; phase: string | null; progress: number | null; diagnostic_id: string; message: string | null }>
  embedding_model_state: string
  embedding_model_error_code: string | null
  operation_in_progress: boolean
  can_retry_failed: boolean
  can_rebuild: boolean
}

const emptyIndexStatus: MockIndexStatus = {
  knowledge_base_id: 'kb-1', status: 'EMPTY', active_index_version_id: null,
  active_index_version_status: null, target_index_version_id: null,
  target_index_version_status: null, target_stage: null,
  file_counts: { total: 0, available: 0, processing: 0, failed: 0 },
  failures: [], tasks: [], embedding_model_state: 'MISSING_OFFLINE',
  embedding_model_error_code: null, operation_in_progress: false,
  can_retry_failed: false, can_rebuild: false,
}

describe('stage 5 knowledge base foundation', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders persisted knowledge bases and navigates to detail', async () => {
    window.history.pushState({}, '', '/knowledge-bases')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/index-status')) return response(emptyIndexStatus)
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
      if (url.endsWith('/index-status')) return response(emptyIndexStatus)
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
      if (url.endsWith('/index-status')) return response(emptyIndexStatus)
      if (url.endsWith('/api/v1/knowledge-bases/kb-1') && init?.method === 'PATCH') {
        patchBody = JSON.parse(String(init.body)) as Record<string, unknown>
        return response({ ...baseItem, ...patchBody, row_version: 4 })
      }
      if (url.endsWith('/api/v1/knowledge-bases/kb-1/files')) return response({ items: [] })
      if (url.includes('/api/v1/files?sort=name')) return response({ items: [], next_cursor: null })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response(baseItem)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('尚未加入任何文件。')).toBeInTheDocument()
    expect(screen.getByText('索引待开放')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: '知识库描述' }), { target: { value: '新说明' } })
    fireEvent.click(screen.getByRole('button', { name: '保存更改' }))

    await waitFor(() => expect(patchBody).toMatchObject({ description: '新说明', row_version: 3 }))
  })

  it('adds imported files, shows persisted task results, and removes a member', async () => {
    window.history.pushState({}, '', '/knowledge-bases/kb-1')
    let addBody: Record<string, unknown> | undefined
    let removed = false
    let taskPolls = 0
    const file = {
      file_id: 'file-1', display_name: '讲义.txt', document_type: 'TXT', status: 'PARSED',
      extension: '.txt', folder_id: null, tags: [], byte_size: 12, content_hash: 'hash',
      created_at: '2026-09-23T00:00:00Z', updated_at: '2026-09-23T00:00:00Z',
      deleted_at: null, purge_after: null, row_version: 1,
    }
    const member = {
      knowledge_base_file_id: 'member-1', file_id: 'file-1', display_name: '讲义.txt',
      document_type: 'TXT', file_status: 'PARSED', membership_status: 'ACTIVE',
      index_state: 'PENDING', available_for_retrieval: false, unavailable_reason: '索引待建立',
      added_at: '2026-09-23T00:00:00Z',
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/index-status')) return response({
        ...emptyIndexStatus,
        status: 'PREPARING',
        file_counts: { total: taskPolls > 0 && !removed ? 1 : 0, available: 0, processing: taskPolls > 0 && !removed ? 1 : 0, failed: 0 },
      })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1/files') && init?.method === 'POST') {
        addBody = JSON.parse(String(init.body)) as Record<string, unknown>
        return response({ task_id: 'task-1', status: 'QUEUED', phase: null, progress: 0, knowledge_base_id: 'kb-1', items: [], results: [], summary: null, error: null }, 202)
      }
      if (url.endsWith('/api/v1/tasks/task-1')) {
        taskPolls += 1
        return response({ task_id: 'task-1', status: 'COMPLETED', phase: 'COMPLETED', progress: 100, knowledge_base_id: 'kb-1', items: [], results: [{ file_id: 'file-1', display_name: '讲义.txt', status: 'ADDED', message: '成员已加入，索引仍待建立。' }], summary: { added: 1, failed: 0 }, error: null })
      }
      if (url.endsWith('/api/v1/knowledge-bases/kb-1/files/file-1') && init?.method === 'DELETE') {
        removed = true
        return response({ knowledge_base_id: 'kb-1', file_id: 'file-1', status: 'REMOVED' })
      }
      if (url.endsWith('/api/v1/knowledge-bases/kb-1/files')) return response({ items: taskPolls > 0 && !removed ? [member] : [] })
      if (url.includes('/api/v1/files?sort=name')) return response({ items: removed ? [file] : taskPolls > 0 ? [] : [file], next_cursor: null })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response({ ...baseItem, status: taskPolls > 0 ? 'PREPARING' : 'EMPTY', file_count: taskPolls > 0 && !removed ? 1 : 0, row_version: taskPolls > 0 ? 4 : 3 })
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: '加入 1 个' }))
    await waitFor(() => expect(addBody).toEqual({ file_ids: ['file-1'] }))
    expect(await screen.findByText('讲义.txt：成员已加入，索引仍待建立。')).toBeInTheDocument()
    const removeButton = await screen.findByRole('button', { name: '移出知识库 讲义.txt' })
    fireEvent.click(removeButton)
    await waitFor(() => expect(removed).toBe(true))
  })

  it('retries failed files, cancels the persisted stage, and confirms full rebuild', async () => {
    window.history.pushState({}, '', '/knowledge-bases/kb-1')
    vi.stubGlobal('confirm', vi.fn(() => true))
    let status = {
      ...emptyIndexStatus,
      status: 'FAILED',
      file_counts: { total: 1, available: 0, processing: 0, failed: 1 },
      failures: [{ file_id: 'failed-1', display_name: '失败资料.txt', stage: 'EMBEDDING', reason_code: 'MODEL_MISSING_OFFLINE', message: '本地模型缺失。', retryable: true, diagnostic_id: 'diag-1' }],
      can_retry_failed: true,
      can_rebuild: true,
    }
    const calls: Array<{ url: string; method?: string; body?: unknown }> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/index-status')) return response(status)
      if (url.endsWith('/index/retry-failed') && init?.method === 'POST') {
        calls.push({ url, method: init.method, body: JSON.parse(String(init.body)) })
        status = {
          ...status,
          operation_in_progress: true,
          can_retry_failed: false,
          can_rebuild: false,
          target_index_version_id: 'version-new',
          target_index_version_status: 'BUILDING',
          target_stage: 'PREPROCESSING',
          tasks: [{ task_id: 'task-retry', task_type: 'INDEX_PREPROCESS', status: 'QUEUED', phase: 'QUEUED', progress: null, diagnostic_id: 'task-retry', message: null }],
        }
        return response({ task_id: 'task-retry', task_type: 'INDEX_PREPROCESS', status: 'QUEUED', phase: 'QUEUED', progress: null, knowledge_base_id: 'kb-1', index_version_id: null, items: [], results: [], summary: null, error: null }, 202)
      }
      if (url.endsWith('/tasks/task-retry/cancel') && init?.method === 'POST') {
        calls.push({ url, method: init.method })
        status = {
          ...status,
          operation_in_progress: false,
          can_rebuild: true,
          target_index_version_id: null,
          target_index_version_status: null,
          target_stage: null,
          tasks: [{ task_id: 'task-retry', task_type: 'INDEX_PREPROCESS', status: 'CANCELLED', phase: 'CANCELLED', progress: 0, diagnostic_id: 'task-retry', message: '任务已取消。' }],
        }
        return response({ task_id: 'task-retry', task_type: 'INDEX_PREPROCESS', status: 'CANCELLED', phase: 'CANCELLED', progress: 0, knowledge_base_id: 'kb-1', index_version_id: null, items: [], results: [], summary: null, error: null })
      }
      if (url.endsWith('/index/rebuild') && init?.method === 'POST') {
        calls.push({ url, method: init.method })
        status = {
          ...status,
          operation_in_progress: true,
          can_rebuild: false,
          target_index_version_id: 'version-rebuild',
          target_index_version_status: 'BUILDING',
          target_stage: 'PREPROCESSING',
          tasks: [{ task_id: 'task-rebuild', task_type: 'INDEX_PREPROCESS', status: 'QUEUED', phase: 'QUEUED', progress: null, diagnostic_id: 'task-rebuild', message: null }],
        }
        return response({ task_id: 'task-rebuild', task_type: 'INDEX_PREPROCESS', status: 'QUEUED', phase: 'QUEUED', progress: null, knowledge_base_id: 'kb-1', index_version_id: null, items: [], results: [], summary: null, error: null }, 202)
      }
      if (url.endsWith('/api/v1/knowledge-bases/kb-1/files')) return response({ items: [] })
      if (url.includes('/api/v1/files?sort=name')) return response({ items: [], next_cursor: null })
      if (url.endsWith('/api/v1/knowledge-bases/kb-1')) return response({ ...baseItem, status: 'READY', file_count: 1 })
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('失败资料.txt')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重试失败文件 (1)' }))
    expect(await screen.findByText('诊断 ID：task-retry')).toBeInTheDocument()
    expect(calls.find((call) => call.url.endsWith('/index/retry-failed'))?.body).toEqual({ file_ids: ['failed-1'] })

    fireEvent.click(screen.getByRole('button', { name: '取消准备文件' }))
    expect(await screen.findByText('任务已取消。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重建当前知识库索引' }))
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('已有活动版本会继续用于检索'))
    expect(await screen.findByText('诊断 ID：task-rebuild')).toBeInTheDocument()
    expect(calls.some((call) => call.url.endsWith('/index/rebuild'))).toBe(true)
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
