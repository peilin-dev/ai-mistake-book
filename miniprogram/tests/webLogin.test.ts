import { beforeEach, describe, expect, it, vi } from 'vitest'

const taro = vi.hoisted(() => ({
  request: vi.fn(),
  login: vi.fn(),
  getStorageSync: vi.fn(),
  setStorageSync: vi.fn(),
}))
vi.mock('@tarojs/taro', () => ({ default: taro }))

import { ApiError } from '../src/lib/api'
import { cancelTicket, confirmTicket, scanTicket, ticketFromScene, webLoginErrorText } from '../src/lib/webLogin'

const BASE = 'http://127.0.0.1:8000'
const T = 'AbCdEfGh12345_-x'

beforeEach(() => {
  vi.resetAllMocks()
  taro.getStorageSync.mockReturnValue('tok')
})

describe('ticketFromScene', () => {
  it('decodes and validates', () => {
    expect(ticketFromScene(T)).toBe(T)
    expect(ticketFromScene(encodeURIComponent(T))).toBe(T)
    expect(ticketFromScene(undefined)).toBeNull()
    expect(ticketFromScene('')).toBeNull()
    expect(ticketFromScene('short')).toBeNull()
    expect(ticketFromScene(`${T}x`)).toBeNull()
    expect(ticketFromScene('abcdefgh1234567!')).toBeNull()
    expect(ticketFromScene('%E0%A4%A')).toBeNull()
  })
})

describe('webLoginErrorText', () => {
  it('maps 410 and 409', () => {
    expect(webLoginErrorText(new ApiError(410, 'x'))).toBe('二维码已过期，请在电脑上刷新')
    expect(webLoginErrorText(new ApiError(409, 'x'))).toBe('这个二维码已经被使用，请在电脑上刷新')
    expect(webLoginErrorText(new ApiError(0, 'request:fail'))).toBe('网络不太好，请稍后再试')
  })
})

describe('scan/confirm/cancel', () => {
  it('call the right endpoints', async () => {
    taro.request.mockResolvedValueOnce({ statusCode: 200, data: { pair_code: '0423' } })
    expect(await scanTicket(T)).toEqual({ pair_code: '0423' })
    let req = taro.request.mock.calls[0][0]
    expect(req.method).toBe('POST')
    expect(req.url).toBe(`${BASE}/api/web-login/tickets/${T}:scan`)

    taro.request.mockResolvedValueOnce({ statusCode: 204, data: '' })
    await confirmTicket(T)
    req = taro.request.mock.calls[1][0]
    expect(req.method).toBe('POST')
    expect(req.url).toBe(`${BASE}/api/web-login/tickets/${T}:confirm`)

    taro.request.mockResolvedValueOnce({ statusCode: 204, data: '' })
    await cancelTicket(T)
    req = taro.request.mock.calls[2][0]
    expect(req.url).toBe(`${BASE}/api/web-login/tickets/${T}:cancel`)
  })
})
