import { beforeEach, describe, expect, it, vi } from 'vitest'

const taro = vi.hoisted(() => ({
  request: vi.fn(),
  downloadFile: vi.fn(),
  openDocument: vi.fn(),
  login: vi.fn(),
  getStorageSync: vi.fn(),
  setStorageSync: vi.fn(),
}))
vi.mock('@tarojs/taro', () => ({ default: taro }))

import { ApiError } from '../src/lib/api'
import { exportErrorText, exportPdf, saveSignature } from '../src/lib/export'

const BASE = 'http://127.0.0.1:8000'

beforeEach(() => {
  vi.resetAllMocks()
  taro.getStorageSync.mockReturnValue('tok')
})

describe('exportErrorText', () => {
  it('shows the backend text for 409', () => {
    const msg = '这位同学这次全对，没有错题可以导出'
    expect(exportErrorText(new ApiError(409, msg))).toBe(msg)
  })

  it('falls back to the generic texts otherwise', () => {
    expect(exportErrorText(new ApiError(0, 'request:fail'))).toBe('网络不太好，请稍后再试')
    expect(exportErrorText(new Error('boom'))).toBe('出了点问题，请稍后再试')
  })

  it('treats a failed download as a network problem', () => {
    expect(exportErrorText({ errMsg: 'downloadFile:fail timeout' })).toBe('网络不太好，请稍后再试')
  })
})

describe('exportPdf', () => {
  it('requests, downloads, then opens in order', async () => {
    const order: string[] = []
    taro.request.mockImplementation(async () => {
      order.push('request')
      return { statusCode: 201, data: { url: '/api/files/exports/a.pdf?expires=1&sig=2', filename: 'a.pdf' } }
    })
    taro.downloadFile.mockImplementation(async () => {
      order.push('download')
      return { statusCode: 200, tempFilePath: 'wxfile://tmp/a.pdf' }
    })
    taro.openDocument.mockImplementation(async () => {
      order.push('open')
    })

    await exportPdf(7, 'student', 42)

    expect(order).toEqual(['request', 'download', 'open'])
    const req = taro.request.mock.calls[0][0]
    expect(req.url).toBe(`${BASE}/api/assignments/7/exports`)
    expect(req.method).toBe('POST')
    expect(req.data).toEqual({ kind: 'student', submission_id: 42 })
    expect(taro.downloadFile.mock.calls[0][0].url).toBe(`${BASE}/api/files/exports/a.pdf?expires=1&sig=2`)
    expect(taro.openDocument.mock.calls[0][0]).toEqual({
      filePath: 'wxfile://tmp/a.pdf',
      fileType: 'pdf',
      showMenu: true,
    })
  })

  it('sends a null submission id for class-wide kinds', async () => {
    taro.request.mockResolvedValue({ statusCode: 201, data: { url: '/x.pdf', filename: 'x.pdf' } })
    taro.downloadFile.mockResolvedValue({ statusCode: 200, tempFilePath: 'p' })
    taro.openDocument.mockResolvedValue({})
    await exportPdf(3, 'lecture')
    expect(taro.request.mock.calls[0][0].data).toEqual({ kind: 'lecture', submission_id: null })
  })

  it('stops and throws on a 409 without downloading', async () => {
    taro.request.mockResolvedValue({ statusCode: 409, data: { detail: '没有错题可以导出' } })
    await expect(exportPdf(3, 'class_students')).rejects.toMatchObject({ status: 409 })
    expect(taro.downloadFile).not.toHaveBeenCalled()
    expect(taro.openDocument).not.toHaveBeenCalled()
  })

  it('throws when the download is not a 200', async () => {
    taro.request.mockResolvedValue({ statusCode: 201, data: { url: '/x.pdf', filename: 'x.pdf' } })
    taro.downloadFile.mockResolvedValue({ statusCode: 404, tempFilePath: '' })
    await expect(exportPdf(3, 'lecture')).rejects.toBeTruthy()
    expect(taro.openDocument).not.toHaveBeenCalled()
  })
})

describe('saveSignature', () => {
  it('patches the name, trimmed', async () => {
    taro.request.mockResolvedValue({ statusCode: 200, data: { id: 1, display_name: '王老师', last_subject: null } })
    const me = await saveSignature('  王老师 ')
    const req = taro.request.mock.calls[0][0]
    expect(req.method).toBe('PATCH')
    expect(req.url).toBe(`${BASE}/api/me`)
    expect(req.data).toEqual({ display_name: '王老师' })
    expect(me.display_name).toBe('王老师')
  })
})
