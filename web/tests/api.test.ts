import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, errorText, request, setOnUnauthorized } from '../src/lib/api'
import { getToken, setToken } from '../src/lib/auth'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('test_401_clears_token_and_redirects', async () => {
    setToken('abc')
    const cb = vi.fn()
    setOnUnauthorized(cb)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, { detail: '请重新登录' })))
    await expect(request('GET', '/api/me')).rejects.toMatchObject({ status: 401 })
    expect(getToken()).toBeNull()
    expect(cb).toHaveBeenCalledTimes(1)
  })

  it('sends bearer token', async () => {
    setToken('abc')
    const f = vi.fn().mockResolvedValue(jsonResponse(200, { id: 1 }))
    vi.stubGlobal('fetch', f)
    await request('GET', '/api/me')
    expect(f.mock.calls[0][1].headers.Authorization).toBe('Bearer abc')
  })

  it('errorText maps network and detail', () => {
    expect(errorText(new TypeError('Failed to fetch'))).toBe('网络不太好，请稍后再试')
    expect(errorText(new ApiError(409, '作业已关闭'))).toBe('作业已关闭')
    expect(errorText(new ApiError(500, 'Internal Server Error'))).toBe('出了点问题，请稍后再试')
    expect(errorText(new Error('x'))).toBe('出了点问题，请稍后再试')
  })
})