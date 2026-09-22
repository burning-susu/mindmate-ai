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

let sessionPromise: Promise<void> | null = null

export async function ensureLocalSession(): Promise<void> {
  if (!sessionPromise) {
    sessionPromise = fetch('/api/v1/system/session', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Request-ID': uuidv7() },
    }).then(async (response) => {
      if (!response.ok) {
        sessionPromise = null
        throw new Error('无法建立本地会话')
      }
    })
  }
  return sessionPromise
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  await ensureLocalSession()
  const headers = new Headers(init.headers)
  headers.set('X-Request-ID', uuidv7())
  if (init.method && !['GET', 'HEAD', 'OPTIONS'].includes(init.method.toUpperCase())) {
    headers.set('Idempotency-Key', uuidv7())
  }
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: 'same-origin',
    cache: 'no-store',
  })
  if (!response.ok) {
    const problem = (await response.json()) as ProblemDetail
    throw new ApiError(response.status, problem)
  }
  return (await response.json()) as T
}
