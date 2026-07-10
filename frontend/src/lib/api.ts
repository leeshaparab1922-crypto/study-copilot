import type { z } from 'zod'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** Thrown for both transport failures and non-2xx HTTP responses. httpStatus
 * is null only for network-level failures (no response at all) — for a real
 * backend response, it's always the actual status code, including 404/409/
 * 422/502 from backend/errors.py's classify_job_exception mapping. */
export class ApiError extends Error {
  httpStatus: number | null
  detail: unknown

  constructor(message: string, httpStatus: number | null, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.httpStatus = httpStatus
    this.detail = detail
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  /** Bearer token asserting student ownership (see backend/auth.py's
   * require_owner) — sent as `Authorization: Bearer <token>` when present.
   * Optional in TYPE terms so existing call sites (e.g. POST /auth/token
   * itself) keep compiling without one, but every route guarded by
   * require_owner will 401 without it. */
  token?: string | null
}

async function request<T>(path: string, schema: z.ZodType<T>, options: RequestOptions = {}): Promise<T> {
  let response: Response
  try {
    const headers: Record<string, string> = {}
    if (options.body !== undefined) headers['Content-Type'] = 'application/json'
    if (options.token) headers['Authorization'] = `Bearer ${options.token}`

    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch (cause) {
    throw new ApiError('Could not reach the server. Check your connection and try again.', null, cause)
  }

  if (!response.ok) {
    let detail: unknown
    try {
      detail = await response.json()
    } catch {
      detail = undefined
    }
    const message =
      (detail && typeof detail === 'object' && 'detail' in detail && typeof detail.detail === 'string'
        ? detail.detail
        : undefined) ?? `Request failed (${response.status})`
    throw new ApiError(message, response.status, detail)
  }

  const json = await response.json()
  const parsed = schema.safeParse(json)
  if (!parsed.success) {
    throw new ApiError('Server returned data in an unexpected shape.', response.status, parsed.error)
  }
  return parsed.data
}

export const api = {
  get: <T>(path: string, schema: z.ZodType<T>, token?: string | null) =>
    request(path, schema, { method: 'GET', token }),
  post: <T>(path: string, schema: z.ZodType<T>, body?: unknown, token?: string | null) =>
    request(path, schema, { method: 'POST', body, token }),
  patch: <T>(path: string, schema: z.ZodType<T>, body?: unknown, token?: string | null) =>
    request(path, schema, { method: 'PATCH', body, token }),
}
