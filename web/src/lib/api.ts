import { clearToken, getToken } from './auth'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

let onUnauthorized: () => void = () => {}

export function setOnUnauthorized(fn: () => void): void {
  onUnauthorized = fn
}

export async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const multipart = body instanceof FormData
  if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json'
  const res = await fetch(path, {
    method,
    headers,
    signal,
    body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') detail = data.detail
    } catch {
      /* non-JSON body */
    }
    if (res.status === 401 && !path.startsWith('/api/auth/')) {
      clearToken()
      onUnauthorized()
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const HAS_CJK = /[\u4e00-\u9fff]/

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 404 || e.status === 422) return '找不到这份内容（可能不是你的班级，或已经删除）'
    return HAS_CJK.test(e.detail) ? e.detail : '出了点问题，请稍后再试'
  }
  if (e instanceof TypeError) return '网络不太好，请稍后再试'
  return '出了点问题，请稍后再试'
}
