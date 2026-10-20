import { beforeEach, describe, expect, it, vi } from 'vitest'

const taro = vi.hoisted(() => ({
  request: vi.fn(),
  uploadFile: vi.fn(),
  login: vi.fn(),
  getStorageSync: vi.fn(),
  setStorageSync: vi.fn(),
}))
vi.mock('@tarojs/taro', () => ({ default: taro }))

import { request, upload, ApiError } from '../src/lib/api'

const BASE = 'http://127.0.0.1:8000'

beforeEach(() => {
  vi.resetAllMocks()
  const store: Record<string, string> = {}
  taro.getStorageSync.mockImplementation((k: string) => store[k] ?? '')
  taro.setStorageSync.mockImplementation((k: string, v: string) => {
    store[k] = v
  })
  taro.login.mockResolvedValue({ code: 'wxcode' })
})

describe('api.request', () => {
  it('addsBearerToken', async () => {
    taro.setStorageSync('token', 'abc')
    taro.request.mockResolvedValue({ statusCode: 200, data: { ok: 1 } })
    const out = await request<{ ok: number }>('GET', '/api/me')
    expect(out).toEqual({ ok: 1 })
    const arg = taro.request.mock.calls[0][0]
    expect(arg.url).toBe(`${BASE}/api/me`)
    expect(arg.method).toBe('GET')
    expect(arg.header.Authorization).toBe('Bearer abc')
  })

  it('relogsInOnceOn401', async () => {
    taro.setStorageSync('token', 'old')
    taro.request
      .mockResolvedValueOnce({ statusCode: 401, data: { detail: 'bad token' } })
      .mockResolvedValueOnce({ statusCode: 200, data: { token: 'new', teacher: { id: 1 } } })
      .mockResolvedValueOnce({ statusCode: 200, data: { ok: 2 } })
    const out = await request<{ ok: number }>('GET', '/api/me')
    expect(out).toEqual({ ok: 2 })
    expect(taro.login).toHaveBeenCalledTimes(1)
    expect(taro.setStorageSync).toHaveBeenCalledWith('token', 'new')
    const retry = taro.request.mock.calls[2][0]
    expect(retry.header.Authorization).toBe('Bearer new')
  })

  it('throwsApiErrorOnSecond401', async () => {
    taro.request
      .mockResolvedValueOnce({ statusCode: 401, data: { detail: 'x' } })
      .mockResolvedValueOnce({ statusCode: 200, data: { token: 'new' } })
      .mockResolvedValueOnce({ statusCode: 401, data: { detail: 'still bad' } })
    await expect(request('GET', '/api/me')).rejects.toMatchObject({ status: 401, detail: 'still bad' })
    expect(taro.login).toHaveBeenCalledTimes(1)
    await expect(Promise.reject(new ApiError(401, 'x'))).rejects.toBeInstanceOf(ApiError)
  })

  it('mapsNon2xxToApiError', async () => {
    taro.request.mockResolvedValue({ statusCode: 409, data: { detail: 'student has results' } })
    const err = (await request('DELETE', '/api/students/1').catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(409)
    expect(err.detail).toBe('student has results')
  })

  it('sendsJsonBody', async () => {
    taro.request.mockResolvedValue({ statusCode: 201, data: { id: 5 } })
    await request('POST', '/api/classes', { name: 'a', grade: 3 })
    expect(taro.request.mock.calls[0][0].data).toEqual({ name: 'a', grade: 3 })
  })
})

describe('api.upload', () => {
  it('uploadsFileFieldWithToken', async () => {
    taro.setStorageSync('token', 'abc')
    taro.uploadFile.mockResolvedValue({ statusCode: 201, data: JSON.stringify({ page_id: 9 }) })
    const out = await upload<{ page_id: number }>('/api/assignments/1/pages', '/tmp/a.jpg')
    expect(out).toEqual({ page_id: 9 })
    const arg = taro.uploadFile.mock.calls[0][0]
    expect(arg.url).toBe(`${BASE}/api/assignments/1/pages`)
    expect(arg.name).toBe('file')
    expect(arg.filePath).toBe('/tmp/a.jpg')
    expect(arg.header.Authorization).toBe('Bearer abc')
  })

  it('mapsUploadErrorToApiError', async () => {
    taro.uploadFile.mockResolvedValue({ statusCode: 503, data: JSON.stringify({ detail: 'queue down' }) })
    await expect(upload('/api/assignments/1/pages', '/tmp/a.jpg')).rejects.toMatchObject({
      status: 503,
      detail: 'queue down',
    })
  })
})
