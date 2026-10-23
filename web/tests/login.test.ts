import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { qrDataUrl, startPolling, type Ticket } from '../src/lib/login'

const ticket: Ticket = { ticket: 't1', poll_key: 'k1', pair_code: '1234', qr_png: '', expires_in: 300 }

function poll(status: string, extra: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({ status, expires_in: 100, token: null, teacher: null, ...extra }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )
}

describe('startPolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('startPolling stops after token', async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(poll('pending'))
      .mockResolvedValueOnce(poll('confirmed', { token: 'tok', teacher: { id: 1, display_name: 'A' } }))
      .mockResolvedValue(poll('expired'))
    vi.stubGlobal('fetch', f)
    const onState = vi.fn()
    const onToken = vi.fn()
    startPolling(ticket, onState, onToken, 2000)
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(2000)
    expect(onToken).toHaveBeenCalledWith('tok')
    await vi.advanceTimersByTimeAsync(10000)
    expect(f).toHaveBeenCalledTimes(2)
    expect(onToken).toHaveBeenCalledTimes(1)
  })

  it('startPolling reports scanned then expired and stops', async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(poll('scanned'))
      .mockResolvedValueOnce(poll('expired'))
      .mockResolvedValue(poll('expired'))
    vi.stubGlobal('fetch', f)
    const onState = vi.fn()
    const onToken = vi.fn()
    startPolling(ticket, onState, onToken, 2000)
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(10000)
    expect(onState.mock.calls.map((c) => c[0])).toEqual(['scanned', 'expired'])
    expect(onToken).not.toHaveBeenCalled()
    expect(f).toHaveBeenCalledTimes(2)
  })

  it('stop function halts polling', async () => {
    const f = vi.fn().mockResolvedValue(poll('pending'))
    vi.stubGlobal('fetch', f)
    const stop = startPolling(ticket, vi.fn(), vi.fn(), 2000)
    await vi.advanceTimersByTimeAsync(2000)
    stop()
    await vi.advanceTimersByTimeAsync(10000)
    expect(f).toHaveBeenCalledTimes(1)
  })
})

describe('qrDataUrl', () => {
  it('uses jpeg for FF D8 magic bytes', () => {
    const b64 = btoa(String.fromCharCode(0xff, 0xd8, 0xff, 0xe0))
    expect(qrDataUrl(b64)).toBe('data:image/jpeg;base64,' + b64)
  })
  it('falls back to png', () => {
    const b64 = btoa(String.fromCharCode(0x89, 0x50, 0x4e, 0x47))
    expect(qrDataUrl(b64)).toBe('data:image/png;base64,' + b64)
  })
})