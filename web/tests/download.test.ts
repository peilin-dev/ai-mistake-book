import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/lib/api', () => ({ request: vi.fn() }))

import { request } from '../src/lib/api'
import { exportAndDownload, needsSignature, practiceReady } from '../src/lib/download'

const req = request as unknown as ReturnType<typeof vi.fn>
afterEach(() => {
  req.mockReset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('exportAndDownload', () => {
  it('posts kind and include_answers then saves blob with filename', async () => {
    req.mockResolvedValue({ url: '/api/files/abc?sig=1', filename: '讲评单.pdf' })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(new Blob(['x'])) })
    vi.stubGlobal('fetch', fetchMock)
    URL.createObjectURL = vi.fn(() => 'blob:1')
    URL.revokeObjectURL = vi.fn()
    const clicked: { download: string; href: string }[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ download: this.download, href: this.href })
    })

    await exportAndDownload(5, 'practice', true)

    expect(req).toHaveBeenCalledWith('POST', '/api/assignments/5/exports', { kind: 'practice', include_answers: true })
    expect(fetchMock).toHaveBeenCalledWith('/api/files/abc?sig=1')
    expect(clicked).toEqual([{ download: '讲评单.pdf', href: 'blob:1' }])
  })

  it('does not send include_answers for other kinds', async () => {
    req.mockResolvedValue({ url: '/api/files/a', filename: 'a.pdf' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(new Blob(['x'])) }))
    URL.createObjectURL = vi.fn(() => 'blob:1')
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await exportAndDownload(5, 'lecture')
    expect(req).toHaveBeenCalledWith('POST', '/api/assignments/5/exports', { kind: 'lecture' })
  })
})

describe('practiceReady', () => {
  it('practice disabled when 404 or not done', async () => {
    req.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 404 }))
    expect(await practiceReady(1)).toBe(false)
    req.mockResolvedValueOnce({ status: 'generating' })
    expect(await practiceReady(1)).toBe(false)
    req.mockResolvedValueOnce({ status: 'done' })
    expect(await practiceReady(1)).toBe(true)
  })
})

describe('needsSignature', () => {
  it('is true for null or blank names', () => {
    expect(needsSignature({ display_name: null })).toBe(true)
    expect(needsSignature({ display_name: '  ' })).toBe(true)
    expect(needsSignature({ display_name: '王老师' })).toBe(false)
  })
})
