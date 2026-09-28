import { v7 as uuidv7 } from 'uuid'

export type ProblemDetail = {
  type: string
  title: string
  status: number
  code: string
  detail: string
  instance: string
  request_id: string
  retryable: boolean
  field_errors: Array<{ field?: string; message?: string; code?: string }>
  actions: Array<{ type: string; resource_id?: string }>
}

export class ApiError extends Error {
  readonly status: number
  readonly problem: ProblemDetail

  constructor(status: number, problem: ProblemDetail) {
    super(problem.detail)
    this.status = status
    this.problem = problem
    this.name = 'ApiError'
  }
}

export class LocalBackendUnavailableError extends Error {
  constructor(message = '本地服务暂时不可用，请启动本地 API 后重新连接。') {
    super(message)
    this.name = 'LocalBackendUnavailableError'
  }
}

export function isLocalBackendUnavailable(error: unknown): boolean {
  return error instanceof LocalBackendUnavailableError
    || (error instanceof ApiError && ['LOCAL_RUNTIME_UNAVAILABLE', 'LOCAL_SESSION_UNAVAILABLE'].includes(error.problem.code))
}

async function readProblem(response: Response): Promise<ProblemDetail> {
  const fallback: ProblemDetail = {
    type: 'about:blank',
    title: '请求失败',
    status: response.status,
    code: 'REQUEST_FAILED',
    detail: '请求没有完成，请稍后重试。',
    instance: '',
    request_id: '',
    retryable: response.status >= 500,
    field_errors: [],
    actions: [],
  }
  try {
    const payload = await response.json() as Partial<ProblemDetail>
    if (typeof payload.detail === 'string') {
      return {
        ...fallback,
        ...payload,
        status: typeof payload.status === 'number' ? payload.status : response.status,
        code: typeof payload.code === 'string' ? payload.code : fallback.code,
        detail: payload.detail,
        title: typeof payload.title === 'string' ? payload.title : fallback.title,
        retryable: typeof payload.retryable === 'boolean' ? payload.retryable : fallback.retryable,
        field_errors: Array.isArray(payload.field_errors) ? payload.field_errors : [],
        actions: Array.isArray(payload.actions) ? payload.actions : [],
      }
    }
  } catch {
    // Use the fixed fallback below when the local server did not return problem+json.
  }
  return fallback
}

let sessionPromise: Promise<void> | null = null

export function clearLocalSessionCache(): void {
  sessionPromise = null
}

export async function ensureLocalSession(): Promise<void> {
  if (!sessionPromise) {
    sessionPromise = fetch('/api/v1/system/session', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Request-ID': uuidv7() },
    }).then(async (response) => {
      if (!response.ok) {
        const problem = await readProblem(response)
        if (response.status >= 500 || problem.code.startsWith('LOCAL_')) {
          throw new ApiError(response.status, problem)
        }
        throw new LocalBackendUnavailableError('无法建立本地会话，请重新连接。')
      }
    }).catch((error: unknown) => {
      sessionPromise = null
      if (error instanceof ApiError || error instanceof LocalBackendUnavailableError) throw error
      throw new LocalBackendUnavailableError()
    })
  }
  return sessionPromise
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  await ensureLocalSession()
  const headers = new Headers(init.headers)
  headers.set('X-Request-ID', uuidv7())
  if (init.body && typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (init.method && !['GET', 'HEAD', 'OPTIONS'].includes(init.method.toUpperCase()) && !headers.has('Idempotency-Key')) {
    headers.set('Idempotency-Key', uuidv7())
  }
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
    })
  } catch {
    throw new LocalBackendUnavailableError()
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readProblem(response))
  }
  return (await response.json()) as T
}

export async function apiUpload<T>(
  path: string,
  files: File[],
  fields: Record<string, string | undefined> = {},
): Promise<T> {
  await ensureLocalSession()
  const body = new FormData()
  files.forEach((file) => body.append('files', file, file.name))
  Object.entries(fields).forEach(([key, value]) => {
    if (value !== undefined) body.append(key, value)
  })
  let response: Response
  try {
    response = await fetch(path, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        'X-Request-ID': uuidv7(),
        'Idempotency-Key': uuidv7(),
      },
    })
  } catch {
    throw new LocalBackendUnavailableError()
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readProblem(response))
  }
  return (await response.json()) as T
}
