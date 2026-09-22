import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import App from '../App'

describe('stage 4 file workspace', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders real file controls and empty state', async () => {
    window.history.pushState({}, '', '/files')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let payload: unknown = { status: 'ok', version: '0.1.0' }
      if (url.includes('/system/session')) payload = { status: 'ready' }
      else if (url.includes('/api/v1/files?')) payload = { items: [], next_cursor: null }
      else if (url.endsWith('/api/v1/folders')) payload = { items: [{ folder_id: 'folder-1', parent_folder_id: null, name: '资料', file_count: 0, row_version: 1, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z' }] }
      else if (url.endsWith('/api/v1/tags')) payload = { items: [{ tag_id: 'tag-1', name: '重点', row_version: 1, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z' }] }
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)

    expect(await screen.findByRole('heading', { name: '文件' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: '仅删除目录 资料' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '按标签筛选' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '按类型筛选' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '按状态筛选' })).toBeInTheDocument()
    expect(await screen.findByText('还没有文件')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '回收站' })).toHaveAttribute('href', '/trash')
  })

  it('sends the folder version and shows a conflict reload action', async () => {
    window.history.pushState({}, '', '/files')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const requestedUrls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      requestedUrls.push(url)
      if (url.includes('/system/session')) return new Response(JSON.stringify({ status: 'ready' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.includes('/api/v1/files?')) return new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/folders')) return new Response(JSON.stringify({ items: [{ folder_id: 'folder-7', parent_folder_id: null, name: '冲突目录', file_count: 0, row_version: 7, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z' }] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/tags')) return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      return new Response(JSON.stringify({ type: 'about:blank', title: '文件操作失败', status: 412, code: 'RESOURCE_VERSION_CONFLICT', detail: '数据已更新。', instance: '/api/v1/folders/folder-7', request_id: 'request-1', retryable: false, field_errors: [], actions: [], current_row_version: 8 }), { status: 412, headers: { 'Content-Type': 'application/problem+json' } })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /目录和内容移入回收站/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('文件夹已被其他操作修改')
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument()
    expect(requestedUrls.some((url) => url.includes('expected_version='))).toBe(true)
  })

  it('renders persisted parse failure metadata', async () => {
    window.history.pushState({}, '', '/files/file-failed')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let payload: unknown = { items: [] }
      if (url.includes('/system/session')) payload = { status: 'ready' }
      else if (url.endsWith('/api/v1/files/file-failed')) payload = {
        file_id: 'file-failed', display_name: 'scan.pdf', source_name: 'scan.pdf', extension: '.pdf', document_type: 'PDF', folder_id: null, folder_name: null, status: 'PARSE_FAILED', content_hash: 'abcdef123456', byte_size: 100, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z', deleted_at: null, purge_after: null, row_version: 2, tags: [], parsed_metadata: null, has_parsed_text: false, content_available: true, parse_failure_stage: 'PARSING', parse_error_id: 'PARSER_FAILED', parse_retry_count: 1, can_reprocess: true,
      }
      else if (url.endsWith('/preview')) payload = { preview_available: false, text: null, metadata: null }
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)

    expect(await screen.findByText('PARSER_FAILED')).toBeInTheDocument()
    expect(screen.getByText('失败阶段')).toBeInTheDocument()
    expect(screen.getByText('重试次数')).toBeInTheDocument()
  })
})
