import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import App from '../App'

describe('stage 0 application shell', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('renders the primary navigation', () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      return new Response(JSON.stringify(url.includes('/system/session') ? { status: 'ready' } : { status: 'ok', version: '0.1.0' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }))

    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>,
    )

    expect(screen.getByText('MindMate')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '首页' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '学习' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'AI 对话' })).toBeInTheDocument()
  })
})
