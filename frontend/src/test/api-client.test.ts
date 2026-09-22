import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('stage 4 API client headers', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.unstubAllGlobals()
  })

  it('sets JSON content type for string request bodies', async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push([input, init])
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const { apiRequest } = await import('../api/client')
    await apiRequest('/api/v1/folders', { method: 'POST', body: JSON.stringify({ name: '资料' }) })

    const headers = new Headers(calls[1][1]?.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('Idempotency-Key')).toBeTruthy()
  })

  it('lets the browser set multipart boundaries for uploads', async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push([input, init])
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const { apiUpload } = await import('../api/client')
    await apiUpload('/api/v1/file-imports', [new File(['text'], 'notes.txt', { type: 'text/plain' })])

    const headers = new Headers(calls[1][1]?.headers)
    expect(headers.has('Content-Type')).toBe(false)
    expect(calls[1][1]?.body).toBeInstanceOf(FormData)
  })
})
