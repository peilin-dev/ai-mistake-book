import Taro from '@tarojs/taro'
import { login, getToken } from './auth'
import { API_BASE } from './config'

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

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

function detailOf(data: unknown): string {
  const d = (data as { detail?: unknown } | null | undefined)?.detail
  if (typeof d === 'string') return d
  if (d !== undefined && d !== null) return JSON.stringify(d)
  return ''
}

function parseBody(data: unknown): unknown {
  if (typeof data !== 'string') return data
  try {
    return JSON.parse(data)
  } catch {
    return data
  }
}

function authHeader(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** Run `send` once; on a 401 log in again silently and retry exactly once. */
async function withRelogin<T>(send: () => Promise<{ statusCode: number; data: unknown }>): Promise<T> {
  let res = await send()
  if (res.statusCode === 401) {
    await login()
    res = await send()
  }
  const data = parseBody(res.data)
  if (res.statusCode < 200 || res.statusCode >= 300) {
    throw new ApiError(res.statusCode, detailOf(data))
  }
  return data as T
}

export function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  return withRelogin<T>(() =>
    Taro.request({
      url: `${API_BASE}${path}`,
      method,
      data: body,
      header: { 'Content-Type': 'application/json', ...authHeader() },
    }),
  )
}

export function upload<T>(path: string, filePath: string): Promise<T> {
  return withRelogin<T>(() =>
    Taro.uploadFile({
      url: `${API_BASE}${path}`,
      filePath,
      name: 'file',
      header: authHeader(),
    }),
  )
}