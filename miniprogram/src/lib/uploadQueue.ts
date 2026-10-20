import { ApiError } from './api'
import { errorText, isNetworkError } from './messages'

export type Uploader = (filePath: string) => Promise<{ page_id: number; seq: number; duplicate: boolean }>

export type QueueState = 'waiting' | 'uploading' | 'done' | 'failed' | 'held' | 'skipped'

export interface QueueItem {
  localId: string
  filePath: string
  state: QueueState
  pageId?: number
  message?: string
}

const QUOTA_TEXT = '本月批改额度已用完'
const RECEIVED_TEXT = '已收到，稍后会自动开始批改'
const SKIPPED_TEXT = '已跳过，这张需要重新拍'
const RESEND_DELAY_MS = 30_000

function statusOf(e: unknown): number | null {
  return e instanceof ApiError ? e.status : null
}

function isRetryable(e: unknown): boolean {
  if (isNetworkError(e)) return true
  const s = statusOf(e)
  return s !== null && s >= 500
}

export class UploadQueue {
  stopped: null | 'quota' = null
  paused: null | { localId: string; message: string } = null

  private list: QueueItem[] = []
  private listeners = new Set<() => void>()
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private running = false
  private disposed = false
  private nextId = 1
  private readonly retries: number

  constructor(
    private readonly uploader: Uploader,
    opts?: { retries?: number },
  ) {
    this.retries = opts?.retries ?? 2
  }

  add(filePath: string): string {
    const localId = `u${this.nextId++}`
    const item: QueueItem = { localId, filePath, state: 'waiting' }
    if (this.stopped === 'quota') {
      item.state = 'held'
      item.message = QUOTA_TEXT
    }
    this.list.push(item)
    this.emit()
    void this.pump()
    return localId
  }

  items(): QueueItem[] {
    return this.list.map((i) => ({ ...i }))
  }

  pendingCount(): number {
    return this.list.filter((i) => i.state === 'waiting' || i.state === 'uploading').length +
      (this.paused ? 1 : 0)
  }

  retry(localId: string): void {
    if (this.stopped !== null || this.paused?.localId !== localId) return
    const item = this.list.find((i) => i.localId === localId)
    if (!item || item.state !== 'failed') return
    item.state = 'waiting'
    item.message = undefined
    this.paused = null
    this.emit()
    void this.pump()
  }

  skip(localId: string): void {
    if (this.paused?.localId !== localId) return
    const item = this.list.find((i) => i.localId === localId)
    if (!item || item.state !== 'failed') return
    item.state = 'skipped'
    item.message = SKIPPED_TEXT
    this.paused = null
    this.emit()
    void this.pump()
  }
  onChange(cb: () => void): () => void {
    this.listeners.add(cb)
    return () => {
      this.listeners.delete(cb)
    }
  }

  dispose(): void {
    this.disposed = true
    this.timers.forEach((t) => clearTimeout(t))
    this.timers.clear()
    this.listeners.clear()
  }

  private emit(): void {
    for (const cb of [...this.listeners]) {
      try {
        cb()
      } catch (err) {
        console.warn('upload queue listener failed', err)
      }
    }
  }

  private async pump(): Promise<void> {
    if (this.running) return
    this.running = true
    try {
      while (!this.disposed && this.stopped === null && this.paused === null) {
        const item = this.list.find((i) => i.state === 'waiting')
        if (!item) break
        await this.process(item)
      }
    } finally {
      this.running = false
    }
  }

  private async process(item: QueueItem): Promise<void> {
    item.state = 'uploading'
    item.message = undefined
    this.emit()
    let attempt = 0
    for (;;) {
      try {
        const res = await this.uploader(item.filePath)
        item.state = 'done'
        item.pageId = res.page_id
        this.emit()
        return
      } catch (e) {
        if (statusOf(e) === 429) {
          this.stopped = 'quota'
          for (const i of this.list) {
            if (i === item || i.state === 'waiting') {
              i.state = 'held'
              i.message = QUOTA_TEXT
            }
          }
          this.emit()
          return
        }
        if (statusOf(e) === 503) {
          item.state = 'done'
          item.message = RECEIVED_TEXT
          this.emit()
          this.scheduleResend(item.filePath)
          return
        }
        if (isRetryable(e) && attempt < this.retries && !this.disposed) {
          attempt++
          continue
        }
        item.state = 'failed'
        item.message = errorText(e)
        this.paused = { localId: item.localId, message: item.message }
        this.emit()
        return
      }
    }
  }

  private scheduleResend(filePath: string): void {
    if (this.disposed) return
    const t = setTimeout(() => {
      this.timers.delete(t)
      if (this.disposed) return
      this.uploader(filePath).catch((e) => console.warn('silent re-upload failed', e))
    }, RESEND_DELAY_MS)
    this.timers.add(t)
  }
}

