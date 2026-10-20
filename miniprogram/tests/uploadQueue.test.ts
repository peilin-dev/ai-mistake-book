import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@tarojs/taro', () => ({ default: {} }))

import { ApiError } from '../src/lib/api'
import { UploadQueue, type Uploader } from '../src/lib/uploadQueue'

const ok = (n = 1) => ({ page_id: n, seq: n, duplicate: false })
const flush = async () => {
  for (let i = 0; i < 20; i++) await Promise.resolve()
}

afterEach(() => {
  vi.useRealTimers()
})

describe('UploadQueue', () => {
  it('uploadsInOrderOneAtATime', async () => {
    const calls: string[] = []
    let active = 0
    let maxActive = 0
    const resolvers: Array<() => void> = []
    const uploader: Uploader = (f) => {
      calls.push(f)
      active++
      maxActive = Math.max(maxActive, active)
      return new Promise((res) => {
        resolvers.push(() => {
          active--
          res(ok(calls.length))
        })
      })
    }
    const q = new UploadQueue(uploader)
    q.add('a')
    q.add('b')
    q.add('c')
    await flush()
    expect(calls).toEqual(['a'])
    expect(q.items().map((i) => i.state)).toEqual(['uploading', 'waiting', 'waiting'])
    resolvers[0]()
    await flush()
    expect(calls).toEqual(['a', 'b'])
    resolvers[1]()
    await flush()
    resolvers[2]()
    await flush()
    expect(calls).toEqual(['a', 'b', 'c'])
    expect(maxActive).toBe(1)
    expect(q.items().every((i) => i.state === 'done')).toBe(true)
    expect(q.pendingCount()).toBe(0)
  })

  it('retriesTwiceThenFails', async () => {
    const uploader = vi.fn<Uploader>().mockRejectedValue(new ApiError(0, ''))
    const q = new UploadQueue(uploader)
    q.add('a')
    await flush()
    expect(uploader).toHaveBeenCalledTimes(3)
    expect(q.items()[0].state).toBe('failed')
    expect(q.items()[0].message).toBe('网络不太好，请稍后再试')
  })

  it('retries 5xx but not 4xx', async () => {
    const u500 = vi.fn<Uploader>().mockRejectedValueOnce(new ApiError(500, 'x')).mockResolvedValue(ok())
    const q1 = new UploadQueue(u500)
    q1.add('a')
    await flush()
    expect(u500).toHaveBeenCalledTimes(2)
    expect(q1.items()[0].state).toBe('done')

    const u413 = vi.fn<Uploader>().mockRejectedValue(new ApiError(413, ''))
    const q2 = new UploadQueue(u413)
    q2.add('a')
    q2.add('b')
    await flush()
    expect(u413).toHaveBeenCalledTimes(2) // a once, b once
    expect(q2.items()[0]).toMatchObject({ state: 'failed', message: '照片太大了，请重拍这张' })

    const u415 = vi.fn<Uploader>().mockRejectedValue(new ApiError(415, ''))
    const q3 = new UploadQueue(u415)
    q3.add('a')
    await flush()
    expect(u415).toHaveBeenCalledTimes(1)
    expect(q3.items()[0].message).toBe('这不是照片，请重拍这张')
  })

  it('manualRetryRequeuesAtSamePosition', async () => {
    const calls: string[] = []
    const failFirst = new Set(['b'])
    const uploader: Uploader = async (f) => {
      calls.push(f)
      if (failFirst.has(f)) throw new ApiError(404, '')
      return ok()
    }
    const q = new UploadQueue(uploader)
    const a = q.add('a')
    const b = q.add('b')
    await flush()
    expect(q.items().map((i) => i.state)).toEqual(['done', 'failed'])
    // block the queue so c stays waiting while b is retried
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    const q2calls: string[] = []
    const q2 = new UploadQueue(async (f) => {
      q2calls.push(f)
      if (f === 'x') await gate
      if (f === 'b' && q2calls.filter((c) => c === 'b').length === 1) throw new ApiError(404, '')
      return ok()
    })
    q2.add('x')
    const b2 = q2.add('b')
    q2.add('c')
    release()
    await flush()
    expect(q2calls).toEqual(['x', 'b', 'c'])
    expect(q2.items().map((i) => i.state)).toEqual(['done', 'failed', 'done'])
    // now add d (waiting behind a held state is not possible); verify retry goes before later waiting items
    const q3calls: string[] = []
    let hold!: () => void
    const gate3 = new Promise<void>((r) => (hold = r))
    const q3 = new UploadQueue(async (f) => {
      q3calls.push(f)
      if (f === 'a') return ok()
      if (f === 'b' && q3calls.filter((c) => c === 'b').length === 1) throw new ApiError(404, '')
      if (f === 'c') await gate3
      return ok()
    })
    q3.add('a')
    const bId = q3.add('b')
    q3.add('c')
    q3.add('d')
    await flush()
    // a done, b failed, c uploading (blocked), d waiting
    expect(q3.items().map((i) => i.state)).toEqual(['done', 'failed', 'uploading', 'waiting'])
    q3.retry(bId)
    expect(q3.items()[1].state).toBe('waiting')
    hold()
    await flush()
    expect(q3calls).toEqual(['a', 'b', 'c', 'b', 'd'])
    expect(a).toBeTruthy()
    expect(b).toBeTruthy()
    expect(b2).toBeTruthy()
  })

  it('duplicateCountsAsDone', async () => {
    const q = new UploadQueue(async () => ({ page_id: 7, seq: 1, duplicate: true }))
    q.add('a')
    await flush()
    expect(q.items()[0]).toMatchObject({ state: 'done', pageId: 7 })
  })

  it('quotaHoldsRemaining', async () => {
    const uploader = vi
      .fn<Uploader>()
      .mockResolvedValueOnce(ok())
      .mockRejectedValueOnce(new ApiError(429, '本月批改额度已用完'))
    const q = new UploadQueue(uploader)
    q.add('a')
    q.add('b')
    q.add('c')
    await flush()
    expect(uploader).toHaveBeenCalledTimes(2)
    expect(q.items().map((i) => i.state)).toEqual(['done', 'held', 'held'])
    expect(q.items()[1].message).toBe('本月批改额度已用完')
    expect(q.stopped).toBe('quota')
    q.add('d')
    await flush()
    expect(uploader).toHaveBeenCalledTimes(2)
    expect(q.items()[3].state).toBe('held')
    expect(q.pendingCount()).toBe(0)
  })

  it('serviceUnavailableMarksDoneAndResendsLater', async () => {
    vi.useFakeTimers()
    const uploader = vi
      .fn<Uploader>()
      .mockRejectedValueOnce(new ApiError(503, '已收到，稍后会自动开始批改'))
      .mockResolvedValue(ok())
    const q = new UploadQueue(uploader)
    q.add('a')
    await vi.advanceTimersByTimeAsync(0)
    expect(q.items()[0]).toMatchObject({ state: 'done', message: '已收到，稍后会自动开始批改' })
    expect(uploader).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(29_000)
    expect(uploader).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1_500)
    expect(uploader).toHaveBeenCalledTimes(2)
    expect(uploader).toHaveBeenLastCalledWith('a')
    await vi.advanceTimersByTimeAsync(120_000)
    expect(uploader).toHaveBeenCalledTimes(2) // only once
  })

  it('dispose cancels pending resend and stops uploading', async () => {
    vi.useFakeTimers()
    const uploader = vi.fn<Uploader>().mockRejectedValueOnce(new ApiError(503, 'x')).mockResolvedValue(ok())
    const q = new UploadQueue(uploader)
    q.add('a')
    await vi.advanceTimersByTimeAsync(0)
    q.dispose()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(uploader).toHaveBeenCalledTimes(1)
    q.add('b')
    await vi.advanceTimersByTimeAsync(0)
    expect(uploader).toHaveBeenCalledTimes(1)
  })

  it('pendingCountForLeaveGuard', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    const q = new UploadQueue(async () => {
      await gate
      return ok()
    })
    q.add('a')
    q.add('b')
    await flush()
    expect(q.pendingCount()).toBe(2) // uploading + waiting
    release()
    await flush()
    expect(q.pendingCount()).toBe(0)
  })

  it('continuesAfterReloginMidQueue', async () => {
    let relogin: Promise<void> | null = null
    let first = true
    const calls: string[] = []
    const uploader: Uploader = async (f) => {
      calls.push(f)
      if (first) {
        first = false
        // api layer: 401 -> silent single-flight re-login -> retry succeeds
        relogin = new Promise((r) => setTimeout(r, 0))
        await relogin
      }
      return ok(calls.length)
    }
    const q = new UploadQueue(uploader)
    q.add('a')
    q.add('b')
    q.add('c')
    await new Promise((r) => setTimeout(r, 10))
    expect(calls).toEqual(['a', 'b', 'c'])
    expect(q.items().every((i) => i.state === 'done')).toBe(true)
  })

  it('onChange fires and unsubscribes', async () => {
    const q = new UploadQueue(async () => ok())
    const cb = vi.fn()
    const off = q.onChange(cb)
    q.add('a')
    await flush()
    expect(cb.mock.calls.length).toBeGreaterThanOrEqual(3) // added, uploading, done
    off()
    const n = cb.mock.calls.length
    q.add('b')
    await flush()
    expect(cb.mock.calls.length).toBe(n)
  })
})
