import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import App from '../App'
import { queryClient } from '../queryClient'

describe('stage 4 file workspace', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    queryClient.clear()
  })

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
    expect(screen.getAllByRole('link', { name: '回收站' })).toEqual(
      expect.arrayContaining([expect.objectContaining({ pathname: '/trash' })]),
    )
  })

  it('updates the visible import task after resolving a duplicate', async () => {
    window.history.pushState({}, '', '/files?folder_id=folder-target')
    const requestedUrls: string[] = []
    let uploadedFolderId: FormDataEntryValue | null = null
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      requestedUrls.push(url)
      if (url.includes('/system/session')) return new Response(JSON.stringify({ status: 'ready' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/health')) return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.includes('/api/v1/files?')) return new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/folders') || url.endsWith('/api/v1/tags')) return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/file-imports') && init?.method === 'POST') {
        uploadedFolderId = (init.body as FormData).get('folder_id')
        return new Response(JSON.stringify({ import_id: 'import-duplicate', task_id: 'import-duplicate', status: 'BLOCKED', phase: 'WAITING_DUPLICATE_DECISION', progress: 100, items: [{ item_index: 0, original_name: 'copy.txt', status: 'BLOCKED', duplicate_status: 'PENDING_DECISION' }] }), { status: 202, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/api/v1/file-imports/import-duplicate')) return new Response(JSON.stringify({ import_id: 'import-duplicate', task_id: 'import-duplicate', status: 'BLOCKED', phase: 'WAITING_DUPLICATE_DECISION', progress: 100, items: [{ item_index: 0, original_name: 'copy.txt', status: 'BLOCKED', duplicate_status: 'PENDING_DECISION' }] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/duplicate-decisions') && init?.method === 'POST') return new Response(JSON.stringify({ import_id: 'import-duplicate', task_id: 'import-duplicate', status: 'COMPLETED', phase: 'COMPLETED', progress: 100, items: [{ item_index: 0, original_name: 'copy.txt', status: 'REUSED', duplicate_status: 'REUSED', file_id: 'restored-file' }] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click((await screen.findAllByRole('button', { name: '导入文件' }))[0])
    const fileInput = document.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    expect(fileInput?.accept).toContain('.xmind')
    expect(fileInput?.accept).toContain('.xmind')
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [new File(['copy'], 'copy.txt', { type: 'text/plain' })] } })

    expect(await screen.findByText('0 个已加入，1 个待决策，0 个失败')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '复用现有' }))
    expect(await screen.findByText('导入任务 已完成')).toBeInTheDocument()
    expect(screen.getByText('1 个已加入，0 个待决策，0 个失败')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '复用现有' })).not.toBeInTheDocument()
    expect(requestedUrls.some((url) => url.endsWith('/duplicate-decisions'))).toBe(true)
    expect(uploadedFolderId).toBe('folder-target')
    expect(requestedUrls.filter((url) => url.endsWith('/api/v1/folders')).length).toBeGreaterThan(1)
  })

  it('accepts file drops across the file workspace', async () => {
    window.history.pushState({}, '', '/files')
    let importedName = ''
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return new Response(JSON.stringify({ status: 'ready' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/health')) return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.includes('/api/v1/files?')) return new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/folders') || url.endsWith('/api/v1/tags')) return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/file-imports') && init?.method === 'POST') {
        importedName = ((init.body as FormData).getAll('files')[0] as File).name
        return new Response(JSON.stringify({ import_id: 'drop-import', task_id: 'drop-import', status: 'COMPLETED', phase: 'COMPLETED', progress: 100, items: [{ item_index: 0, original_name: importedName, status: 'IMPORTED', duplicate_status: 'NOT_DUPLICATE', file_id: 'drop-file', parse_status: 'PARSED' }] }), { status: 202, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/api/v1/file-imports/drop-import')) return new Response(JSON.stringify({ import_id: 'drop-import', task_id: 'drop-import', status: 'COMPLETED', phase: 'COMPLETED', progress: 100, items: [{ item_index: 0, original_name: importedName, status: 'IMPORTED', duplicate_status: 'NOT_DUPLICATE', file_id: 'drop-file', parse_status: 'PARSED' }] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    const workspace = document.querySelector('.files-main')
    expect(workspace).not.toBeNull()
    const droppedFile = new File(['notes'], 'dropped.txt', { type: 'text/plain' })
    const dataTransfer = { files: [droppedFile], types: ['Files'], dropEffect: 'none' }
    fireEvent.dragEnter(workspace as HTMLElement, { dataTransfer })
    expect(await screen.findByText('释放文件以导入')).toBeInTheDocument()

    fireEvent.drop(workspace as HTMLElement, { dataTransfer })
    expect(await screen.findByText('1 个已加入，0 个待决策，0 个失败')).toBeInTheDocument()
    expect(importedName).toBe('dropped.txt')
  })

  it('refreshes global and folder counts after trashing a filtered file', async () => {
    window.history.pushState({}, '', '/files?folder_id=folder-7')
    let activeTotal = 3
    let folderCount = 2
    let folderFiles = [
      { file_id: 'file-7', display_name: 'interview.md', source_name: 'interview.md', extension: '.md', document_type: 'MARKDOWN', folder_id: 'folder-7', folder_name: '面试题', status: 'PARSED', content_hash: 'hash-7', byte_size: 128, created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z', deleted_at: null, purge_after: null, row_version: 2, tags: [], parsed_metadata: null, has_parsed_text: true, content_available: true, parse_failure_stage: null, parse_error_id: null, parse_retry_count: 0, can_reprocess: true },
      { file_id: 'file-8', display_name: 'notes.md', source_name: 'notes.md', extension: '.md', document_type: 'MARKDOWN', folder_id: 'folder-7', folder_name: '面试题', status: 'PARSED', content_hash: 'hash-8', byte_size: 256, created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z', deleted_at: null, purge_after: null, row_version: 1, tags: [], parsed_metadata: null, has_parsed_text: true, content_available: true, parse_failure_stage: null, parse_error_id: null, parse_retry_count: 0, can_reprocess: true },
    ]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return new Response(JSON.stringify({ status: 'ready' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/health')) return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.includes('/api/v1/files?')) return new Response(JSON.stringify({ items: folderFiles, next_cursor: null }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/folders')) return new Response(JSON.stringify({ items: [{ folder_id: 'folder-7', parent_folder_id: null, name: '面试题', file_count: folderCount, row_version: 1, created_at: '2026-10-10T00:00:00Z', updated_at: '2026-10-10T00:00:00Z' }] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/tags')) return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.includes('/api/v1/home/overview')) return new Response(JSON.stringify({ files: activeTotal }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.startsWith('/api/v1/files/file-7?') && init?.method === 'DELETE') {
        folderFiles = folderFiles.filter((file) => file.file_id !== 'file-7')
        folderCount = 1
        activeTotal = 2
        return new Response(JSON.stringify({ file_id: 'file-7', status: 'IN_TRASH' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    const allFilesButton = await screen.findByRole('button', { name: /全部文件/ })
    const folderButtons = await screen.findAllByRole('button', { name: /面试题/ })
    const folderButton = folderButtons.find((button) => button.classList.contains('folder-row'))
    expect(folderButton).toBeDefined()
    const folderCountButton = folderButton as HTMLButtonElement
    expect(allFilesButton.querySelector('small')).toHaveTextContent('3')
    expect(folderCountButton.querySelector('small')).toHaveTextContent('2')

    fireEvent.click(await screen.findByRole('button', { name: '移入回收站 interview.md' }))
    await waitFor(() => expect(allFilesButton.querySelector('small')).toHaveTextContent('2'))
    await waitFor(() => expect(folderCountButton.querySelector('small')).toHaveTextContent('1'))
  })

  it('sends the folder version and shows a conflict reload action', async () => {
    window.history.pushState({}, '', '/files')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const requestedUrls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      requestedUrls.push(url)
      if (url.includes('/system/session')) return new Response(JSON.stringify({ status: 'ready' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/api/v1/health')) return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
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

  it('shows Markdown files in formatted reading mode', async () => {
    window.history.pushState({}, '', '/files/file-markdown')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let payload: unknown = { items: [] }
      if (url.includes('/system/session')) payload = { status: 'ready' }
      else if (url.endsWith('/api/v1/health')) payload = { status: 'ok', version: '0.1.0' }
      else if (url.endsWith('/api/v1/files/file-markdown')) payload = {
        file_id: 'file-markdown', display_name: 'interview.md', source_name: 'interview.md', extension: '.md', document_type: 'MARKDOWN', folder_id: null, folder_name: null, status: 'PARSED', content_hash: 'abcdef123456', byte_size: 42, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z', deleted_at: null, purge_after: null, row_version: 1, tags: [], parsed_metadata: null, has_parsed_text: true, content_available: true, parse_failure_stage: null, parse_error_id: null, parse_retry_count: 0, can_reprocess: true,
      }
      else if (url.endsWith('/preview')) payload = { preview_available: true, text: '# 模块成绩\n\n**结果：** 已通过。', metadata: { line_count: 3, character_count: 20 } }
      else if (url.endsWith('/knowledge-bases')) payload = { items: [] }
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)

    expect(await screen.findByRole('heading', { level: 1, name: '模块成绩' })).toBeInTheDocument()
    expect(screen.getByText('结果：')).toBeInTheDocument()
    expect(document.querySelector('.markdown-preview')).toBeInTheDocument()
    expect(document.querySelector('.text-preview')).not.toBeInTheDocument()
  })

  it('restores list filters, sorting, and scroll position after returning from details', async () => {
    window.history.pushState({}, '', '/files')
    Object.defineProperty(window, 'scrollY', { configurable: true, value: 240 })
    const scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let payload: unknown = { items: [] }
      if (url.includes('/system/session')) payload = { status: 'ready' }
      else if (url.includes('/api/v1/files?')) payload = {
        items: [{ file_id: 'file-1', display_name: 'lecture.txt', source_name: 'lecture.txt', extension: '.txt', document_type: 'TXT', folder_id: null, folder_name: null, status: 'PARSED', content_hash: 'hash', byte_size: 42, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z', deleted_at: null, purge_after: null, row_version: 1, tags: [], parsed_metadata: null, has_parsed_text: true, content_available: true, parse_failure_stage: null, parse_error_id: null, parse_retry_count: 0, can_reprocess: true }], next_cursor: null,
      }
      else if (url.endsWith('/api/v1/folders')) payload = { items: [] }
      else if (url.endsWith('/api/v1/tags')) payload = { items: [] }
      else if (url.endsWith('/api/v1/files/file-1')) payload = { file_id: 'file-1', display_name: 'lecture.txt', source_name: 'lecture.txt', extension: '.txt', document_type: 'TXT', folder_id: null, folder_name: null, status: 'PARSED', content_hash: 'hash', byte_size: 42, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:00Z', deleted_at: null, purge_after: null, row_version: 1, tags: [], parsed_metadata: null, has_parsed_text: true, content_available: true, parse_failure_stage: null, parse_error_id: null, parse_retry_count: 0, can_reprocess: true }
      else if (url.endsWith('/preview')) payload = { preview_available: true, text: 'lecture text', metadata: { line_count: 1, character_count: 12 } }
      else if (url.endsWith('/knowledge-bases')) payload = { items: [] }
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.change(await screen.findByRole('textbox', { name: '搜索文件' }), { target: { value: 'lecture' } })
    fireEvent.change(screen.getByRole('combobox', { name: '排序' }), { target: { value: 'name' } })
    await waitFor(() => expect(window.location.search).toContain('q=lecture'))
    expect(window.location.search).toContain('sort=name')

    fireEvent.click(await screen.findByRole('link', { name: /lecture\.txt/ }))
    expect(await screen.findByRole('heading', { name: 'lecture.txt' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '返回文件' }))
    await screen.findByRole('heading', { name: '文件' })

    await waitFor(() => expect(window.location.search).toContain('q=lecture'))
    expect(window.location.search).toContain('sort=name')
    await waitFor(() => expect(scrollTo).toHaveBeenCalledWith({ top: 240, behavior: 'auto' }))
  })
})
