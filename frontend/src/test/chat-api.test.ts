import { describe, expect, it } from 'vitest'

import { parseSseText } from '../api/chat'

describe('chat SSE parser', () => {
  it('keeps partial lines and supports multi-line data fields', () => {
    const events: Array<{ id: number; data: Record<string, unknown> }> = []
    const first = parseSseText(
      'id: 7\nevent: snapshot\ndata: {"operation_id":"op-1",\n',
      (event) => events.push({ id: event.id, data: event.data }),
    )
    expect(events).toHaveLength(0)
    const second = parseSseText(
      `${first.remainder}data: "content":"value"}\n\n`,
      (event) => events.push({ id: event.id, data: event.data }),
      first.state,
    )
    expect(second.remainder).toBe('')
    expect(events).toEqual([
      { id: 7, data: { operation_id: 'op-1', content: 'value' } },
    ])
  })

  it('ignores comments and emits terminal events without appending text', () => {
    const events: Array<{ event: string; id: number; data: Record<string, unknown> }> = []
    parseSseText(
      ': keep-alive\nid: 8\nevent: completed\ndata: {"status":"COMPLETED","content":"full"}\n\n',
      (event) => events.push({ event: event.event, id: event.id, data: event.data }),
    )
    expect(events).toEqual([
      { event: 'completed', id: 8, data: { status: 'COMPLETED', content: 'full' } },
    ])
  })
})
