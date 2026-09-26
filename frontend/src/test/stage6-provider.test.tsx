import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import App from '../App'
import { queryClient } from '../queryClient'

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  })
}

type FixtureProbe = {
  status: 'success' | 'failed'
  checked_at: string
  requested_model: string
  resolved_model: string | null
  stream_supported: string
  usage_supported: string
  structured_output_supported: string
  provider_request_id: string | null
  response_fingerprint: string | null
  usage: Record<string, number> | null
  error_code: string | null
  error_detail: string | null
  retryable: boolean | null
}

type FixtureStatus = {
  provider: string
  display_name: string
  configured: boolean
  credential_store: { available: boolean; type: string; error_code: string | null }
  requested_model: string
  consent: { current_version: string; accepted: boolean; version: string | null; accepted_at: string | null }
  probe: FixtureProbe | null
  source_url: string
  pricing_url: string
  generation_mode?: 'mock' | 'deepseek'
  cost_estimate?: {
    disclaimer: string
    knowledge_question_estimated_usd_ceiling: string
    probe_estimated_usd_ceiling: string
    rate_assumption: string
  }
}

const initialStatus: FixtureStatus = {
  provider: 'DEEPSEEK',
  display_name: 'DeepSeek',
  configured: false,
  credential_store: { available: true, type: 'windows-credential-manager', error_code: null },
  requested_model: 'deepseek-flash',
  consent: { current_version: 'deepseek-external-ai-v1', accepted: false, version: null, accepted_at: null },
  probe: null,
  source_url: 'https://platform.deepseek.com/api_keys',
  pricing_url: 'https://api-docs.deepseek.com/quick_start/pricing',
}

describe('stage 6 AI provider configuration', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('saves a key, clears the input, and requires explicit probe confirmation', async () => {
    window.history.pushState({}, '', '/settings')
    let currentStatus: FixtureStatus = structuredClone(initialStatus)
    const calls: Array<{ url: string; method?: string; body?: unknown }> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/ai/provider/key') && init?.method === 'POST') {
        calls.push({ url, method: init.method, body: JSON.parse(String(init.body)) })
        currentStatus = { ...currentStatus, configured: true }
        return response(currentStatus)
      }
      if (url.endsWith('/api/v1/ai/provider/test') && init?.method === 'POST') {
        calls.push({ url, method: init.method, body: JSON.parse(String(init.body)) })
        currentStatus = {
          ...currentStatus,
          probe: {
            status: 'success', checked_at: '2026-09-25T09:00:00Z', requested_model: 'deepseek-flash',
            resolved_model: 'deepseek-v4.1-flash', stream_supported: 'supported', usage_supported: 'supported',
            structured_output_supported: 'unknown', provider_request_id: 'probe', response_fingerprint: 'fingerprint',
            usage: { prompt_tokens: 8, completion_tokens: 3, total_tokens: 11 }, error_code: null, error_detail: null, retryable: null,
          },
        }
        return response(currentStatus)
      }
      if (url.endsWith('/api/v1/ai/provider')) return response(currentStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByRole('heading', { name: '设置' })).toBeInTheDocument()
    const keyInput = screen.getByLabelText('DeepSeek API Key')
    fireEvent.change(keyInput, { target: { value: 'fixture-secret' } })
    fireEvent.click(screen.getByRole('button', { name: '保存 Key' }))
    await waitFor(() => expect(keyInput).toHaveValue(''))
    expect(calls[0]).toMatchObject({ body: { api_key: 'fixture-secret' } })
    expect(screen.getByText('已配置')).toBeInTheDocument()

    const testButton = screen.getByRole('button', { name: '测试连接' })
    expect(testButton).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /固定测试文本/ }))
    expect(testButton).toBeEnabled()
    fireEvent.click(testButton)
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/ai/provider/test'))).toBe(true))
    expect(calls.find((call) => call.url.endsWith('/ai/provider/test'))?.body).toEqual({ confirm_external_transfer: true })
    expect(await screen.findByText('deepseek-v4.1-flash')).toBeInTheDocument()
  })

  it('records external AI consent as a separate versioned action', async () => {
    window.history.pushState({}, '', '/settings')
    let currentStatus: FixtureStatus = structuredClone(initialStatus)
    let consentBody: unknown
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/ai/consent') && init?.method === 'POST') {
        consentBody = JSON.parse(String(init.body))
        currentStatus = {
          ...currentStatus,
          consent: { ...currentStatus.consent, accepted: true, version: 'deepseek-external-ai-v1', accepted_at: '2026-09-25T09:00:00Z' },
        }
        return response(currentStatus.consent)
      }
      if (url.endsWith('/api/v1/ai/provider')) return response(currentStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('待确认')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /未来 AI 功能/ }))
    fireEvent.click(screen.getByRole('button', { name: '确认并记录说明版本' }))
    await waitFor(() => expect(consentBody).toEqual({ version: 'deepseek-external-ai-v1' }))
    expect(await screen.findByText(/已记录版本 deepseek-external-ai-v1/)).toBeInTheDocument()
  })

  it('switches generation mode without sending a key or a provider request', async () => {
    window.history.pushState({}, '', '/settings')
    let currentStatus: FixtureStatus = structuredClone(initialStatus)
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/ai/provider/generation-mode') && init?.method === 'POST') {
        calls.push(String(init.body))
        currentStatus = { ...currentStatus, generation_mode: 'deepseek' }
        return response(currentStatus)
      }
      if (url.endsWith('/api/v1/ai/provider')) return response(currentStatus)
      return response({ status: 'ok', version: '0.1.0' })
    }))

    render(<BrowserRouter><App /></BrowserRouter>)
    fireEvent.click(await screen.findByRole('button', { name: '使用 DeepSeek 在线生成' }))
    await waitFor(() => expect(calls).toEqual([JSON.stringify({ mode: 'deepseek' })]))
    expect(await screen.findByText('DeepSeek 在线生成、会外发当前问题与必要的少量证据。')).toBeInTheDocument()
    expect(calls.some((body) => body.includes('api_key'))).toBe(false)
  })

  it('labels mock chat and blocks online send until the user confirms the estimate', async () => {
    queryClient.clear()
    window.history.pushState({}, '', '/chat')
    let mode: 'mock' | 'deepseek' = 'mock'
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/ai/provider')) {
        return response({
          ...initialStatus,
          generation_mode: mode,
          configured: true,
          consent: { ...initialStatus.consent, accepted: true, version: 'deepseek-external-ai-v1' },
          cost_estimate: {
            checked_on: '2026-09-26',
            model: 'deepseek-flash',
            pricing_url: initialStatus.pricing_url,
            rate_assumption: '高峰、缓存未命中',
            input_usd_per_million_tokens: '0.30',
            output_usd_per_million_tokens: '1.20',
            knowledge_input_token_cap: 2048,
            knowledge_output_token_cap: 256,
            knowledge_question_estimated_usd_ceiling: '0.001',
            probe_output_token_cap: 8,
            probe_estimated_usd_ceiling: '0.0001',
            disclaimer: '这是保守估算，不是严格美元限额。',
          },
        })
      }
      if (url.endsWith('/api/v1/conversations')) return response({ items: [] })
      return response({ status: 'ok', version: '0.1.0' })
    }))

    const view = render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('Mock 生成，不会外发，也不会产生 DeepSeek 费用。')).toBeInTheDocument()
    mode = 'deepseek'
    view.unmount()
    queryClient.clear()
    window.history.pushState({}, '', '/chat')
    render(<BrowserRouter><App /></BrowserRouter>)
    expect(await screen.findByText('DeepSeek 在线生成、会外发当前问题与必要的少量证据。')).toBeInTheDocument()
    const send = screen.getByRole('button', { name: '发送' })
    expect(send).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /保守费用估算/ }))
    fireEvent.change(screen.getByLabelText('消息内容'), { target: { value: '短问题' } })
    expect(screen.getByRole('button', { name: '发送' })).toBeEnabled()
  })
})
