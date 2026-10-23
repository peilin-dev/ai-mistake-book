import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/lib/intake', () => ({
  toJpeg: vi.fn(async (b: Blob) => b),
  imageBody: (b: Blob) => b,
}))
vi.mock('../src/lib/api', async () => {
  const actual =
    await vi.importActual<typeof import('../src/lib/api')>('../src/lib/api')
  return { ...actual, request: vi.fn() }
})
import { ApiError, request } from '../src/lib/api'
import { uploadAll, summaryText } from '../src/lib/uploader'
import type { SourcePage } from '../src/lib/intake'
const req = vi.mocked(request)
const pages = (n: number): SourcePage[] =>
  Array.from({ length: n }, (_, i) => ({
    id: String(i),
    fileName: `${i}.jpg`,
    pageNo: null,
    takenAt: null,
    load: async () => new Blob(['jpg']),
  }))
beforeEach(() => req.mockReset())
describe('batch upload', () => {
  it('does not continue in the background after navigation aborts the upload', async () => {
    const controller = new AbortController()
    req.mockImplementation(async () => {
      controller.abort()
      return { duplicate: false }
    })
    await uploadAll(7, pages(5), vi.fn(), 1, controller.signal)
    expect(req).toHaveBeenCalledTimes(1)
  })
  it('limits concurrent requests to three and always marks web source', async () => {
    let active = 0,
      peak = 0
    req.mockImplementation(async () => {
      active++
      peak = Math.max(peak, active)
      await new Promise((r) => setTimeout(r, 5))
      active--
      return { duplicate: false }
    })
    const result = await uploadAll(7, pages(10), vi.fn())
    expect(peak).toBe(3)
    expect(result.uploaded).toBe(10)
    expect(
      req.mock.calls.every(
        ([method, path]) =>
          method === 'POST' && path === '/api/assignments/7/pages?source=web',
      ),
    ).toBe(true)
  })
  it('counts duplicates without treating them as newly uploaded pages', async () => {
    req
      .mockResolvedValueOnce({ duplicate: true })
      .mockResolvedValue({ duplicate: false })
    const change = vi.fn(),
      result = await uploadAll(7, pages(3), change, 1)
    expect(result).toMatchObject({ uploaded: 2, duplicates: 1, failed: 0 })
    expect(change).toHaveBeenCalledWith('0', 'duplicate')
  })
  it('stops dispatching after quota is exhausted and lists every skipped page', async () => {
    req.mockRejectedValueOnce(new ApiError(429, '本月批改额度已用完'))
    const change = vi.fn(),
      result = await uploadAll(7, pages(6), change, 1)
    expect(req).toHaveBeenCalledTimes(1)
    expect(result.skipped).toBe(6)
    expect(
      change.mock.calls.filter((c) => c[1] === 'skipped_quota'),
    ).toHaveLength(6)
    expect(summaryText(result)).toContain('剩下 6 页没有上传')
  })
  it('keeps processing other pages after a network failure', async () => {
    req
      .mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValue({ duplicate: false })
    const result = await uploadAll(7, pages(3), vi.fn(), 1)
    expect(result.failed).toBe(1)
    expect(result.uploaded).toBe(2)
    expect(summaryText(result)).toBe('上传 2 页，跳过重复 0 页，失败 1 页')
  })
})
