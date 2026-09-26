import { v7 as uuidv7 } from 'uuid'

import type { components } from './generated/openapi'
import { ApiError, apiRequest, ensureLocalSession } from './client'

export type Conversation = components['ConversationResponse']
export type Message = components['MessageResponse']
export type Operation = components['AiOperationResponse']
export type Submission = components['ConversationSubmissionResponse']
export type Citation = components['CitationResponse']
export type ChatMode = 'GENERAL_CHAT' | 'KNOWLEDGE_CHAT'

export type ChatEvent = {
  event: string
  id: number
  data: {
    operation_id?: string
    content?: string
    sequence?: number
    event_sequence?: number
    status?: string
    error_code?: string
    terminal?: boolean
    [key: string]: unknown
  }
}

export async function listConversations(): Promise<{ items: Conversation[] }> {
  return apiRequest('/api/v1/conversations')
}

export async function getConversation(conversationId: string): Promise<Conversation> {
  return apiRequest(`/api/v1/conversations/${conversationId}`)
}

export async function listMessages(conversationId: string): Promise<{ items: Message[] }> {
  return apiRequest(`/api/v1/conversations/${conversationId}/messages`)
}

export async function getOperation(operationId: string): Promise<Operation> {
  return apiRequest(`/api/v1/ai-operations/${operationId}`)
}

export async function createConversation(
  content: string,
  options: {
    mode?: ChatMode
    knowledgeBaseId?: string
    idempotencyKey?: string
  } = {},
): Promise<Submission> {
  const idempotencyKey = options.idempotencyKey ?? uuidv7()
  const mode = options.mode ?? 'GENERAL_CHAT'
  return apiRequest('/api/v1/conversations', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({
      first_message: content,
      client_request_id: idempotencyKey,
      mode,
      source_scope: mode === 'KNOWLEDGE_CHAT' && options.knowledgeBaseId
        ? { scope_type: 'KNOWLEDGE_BASE', knowledge_base_id: options.knowledgeBaseId }
        : null,
    }),
  })
}

export async function createMessage(
  conversationId: string,
  content: string,
  expectedConversationVersion: number,
  idempotencyKey = uuidv7(),
): Promise<Submission> {
  return apiRequest(`/api/v1/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({
      content,
      expected_conversation_version: expectedConversationVersion,
      client_request_id: idempotencyKey,
    }),
  })
}

export async function stopOperation(operationId: string): Promise<Operation> {
  return apiRequest(`/api/v1/ai-operations/${operationId}/stop`, { method: 'POST' })
}

function emitEvent(
  eventName: string,
  eventId: string,
  dataLines: string[],
  onEvent: (event: ChatEvent) => void,
): void {
  if (dataLines.length === 0) return
  let data: ChatEvent['data']
  try {
    data = JSON.parse(dataLines.join('\n')) as ChatEvent['data']
  } catch {
    throw new Error('服务端流事件格式无效')
  }
  onEvent({ event: eventName || 'message', id: Number(eventId) || 0, data })
}

export function parseSseText(
  text: string,
  onEvent: (event: ChatEvent) => void,
  state: { eventName?: string; eventId?: string; dataLines?: string[] } = {},
): { remainder: string; state: { eventName?: string; eventId?: string; dataLines?: string[] } } {
  const lines = text.split(/\r?\n/)
  const remainder = lines.pop() ?? ''
  let eventName = state.eventName ?? ''
  let eventId = state.eventId ?? ''
  let dataLines = state.dataLines ?? []
  for (const line of lines) {
    if (line === '') {
      emitEvent(eventName, eventId, dataLines, onEvent)
      eventName = ''
      eventId = ''
      dataLines = []
      continue
    }
    if (line.startsWith(':')) continue
    const separator = line.indexOf(':')
    const field = separator >= 0 ? line.slice(0, separator) : line
    const value = separator >= 0 ? line.slice(separator + 1).replace(/^ /, '') : ''
    if (field === 'event') eventName = value
    else if (field === 'id') eventId = value
    else if (field === 'data') dataLines.push(value)
  }
  return { remainder, state: { eventName, eventId, dataLines } }
}

export async function streamOperation(
  operationId: string,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
  lastEventId?: number,
): Promise<void> {
  await ensureLocalSession()
  const headers = new Headers({
    Accept: 'text/event-stream',
    'X-Request-ID': uuidv7(),
  })
  if (lastEventId && lastEventId > 0) headers.set('Last-Event-ID', String(lastEventId))
  const response = await fetch(`/api/v1/ai-operations/${operationId}/events`, {
    method: 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    headers,
    signal,
  })
  if (!response.ok) {
    let problem: components['ProblemDetail']
    try {
      problem = (await response.json()) as components['ProblemDetail']
    } catch {
      problem = {
        type: 'about:blank',
        title: '流式连接失败',
        status: response.status,
        code: 'CHAT_STREAM_FAILED',
        detail: '无法连接普通聊天流。',
        instance: `/api/v1/ai-operations/${operationId}/events`,
        request_id: uuidv7(),
      }
    }
    throw new ApiError(response.status, problem as never)
  }
  if (!response.body) throw new Error('浏览器不支持流式响应')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let remainder = ''
  let parserState: { eventName?: string; eventId?: string; dataLines?: string[] } = {}
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      const parsed = parseSseText(remainder + decoder.decode(value, { stream: true }), onEvent, parserState)
      remainder = parsed.remainder
      parserState = parsed.state
    }
    const tail = remainder + decoder.decode()
    if (tail) {
      const parsed = parseSseText(`${tail}\n\n`, onEvent, parserState)
      parserState = parsed.state
    } else if (parserState.dataLines?.length) {
      emitEvent(parserState.eventName ?? '', parserState.eventId ?? '', parserState.dataLines, onEvent)
    }
  } finally {
    reader.releaseLock()
  }
}
