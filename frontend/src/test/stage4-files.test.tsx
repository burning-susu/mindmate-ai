import { render, screen } from '@testing-library/react'
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
      else if (url.endsWith('/api/v1/folders')) payload = { items: [{ folder_id: 'folder-1', parent_folder_id: null, name: '资料', file_count: 0 }] }
      else if (url.endsWith('/api/v1/tags')) payload = { items: [{ tag_id: 'tag-1', name: '重点' }] }
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
})
