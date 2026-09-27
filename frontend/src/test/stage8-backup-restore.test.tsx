import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { BackupRestorePanel } from '../pages/BackupRestorePanel'

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const prechecked = {
  restore_available: true,
  phase: 'PRECHECKED',
  precheck_id: 'precheck-1',
  restart_required: false,
  writes_frozen: false,
  provider_reconfirm_required: false,
  recovery_point_available: false,
  confirm_phrase: '覆盖当前全部本地数据',
  overwrite_scope: '整份本地业务数据将被覆盖，不与当前数据合并。',
  summary: {
    executable: true,
    file_count: 2,
    total_size: 128,
    backup_format_version: '1',
    schema_plan: 'same',
    overwrite_scope: '整份本地业务数据将被覆盖，不与当前数据合并。',
    warnings: ['备份未加密，包含私人文件和学习记录。'],
    includes: { secrets: false, vectors: false },
  },
}

describe('backup restore panel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('requires the overwrite phrase before confirmation and then shows restart', async () => {
    let executions = 0
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/system/session')) return response({ status: 'ready' })
      if (url.endsWith('/api/v1/backups/restore/status')) return response(prechecked)
      if (url.endsWith('/api/v1/backups/restore/executions') && init?.method === 'POST') {
        executions += 1
        return response({ ...prechecked, phase: 'RESTART_REQUIRED', restart_required: true, writes_frozen: true })
      }
      return response({ status: 'ok' })
    }))

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <BackupRestorePanel enabled />
      </QueryClientProvider>,
    )

    expect(await screen.findByText(/整份覆盖当前本地资料/)).toBeInTheDocument()
    const confirm = await screen.findByRole('button', { name: '确认恢复并准备重启' })
    expect(confirm).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /整份覆盖当前本地数据/ }))
    fireEvent.change(screen.getByLabelText('恢复确认语'), { target: { value: '覆盖当前全部本地数据' } })
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)
    await waitFor(() => expect(executions).toBe(1))
    expect(await screen.findByText('已确认，等待重启后切换')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认恢复并准备重启' })).toBeDisabled()
  })
})
