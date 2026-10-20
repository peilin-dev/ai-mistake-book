import { ApiError } from './api'
import { errorText, isNetworkError } from './messages'

export type Uploader = (filePath: string) => Promise<{ page_id: number; seq: number; duplicate: boolean }>

export type QueueState = 'waiting' | 'uploading' | 'done' | 'failed' | 'held'

export interface QueueItem {
  localId: string
  filePath: string
  state: QueueState
  pageId?: number
  message?: string
  /** No usable file (the photo could not be processed): only 重拍这张 can fix it. */
  retakeOnly?: boolean
}

const QUOTA_TEXT = '本月批改额度已用完'
const RECEIVED_TEXT = '已收到，稍后会自动开始批改'
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
  /** 503 resends scheduled or in flight; the backend sweep re-enqueues them if we leave. */
  private resends = 0
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

  /**
   * A photo that could not be prepared (e.g. compression failed). It keeps its place in
   * shooting order and pauses the queue when reached, so nothing behind it uploads until
   * it is re-shot: the backend links a nameless page to the page uploaded just before it.
   */
  addFailed(message: string): string {
    const localId = `u${this.nextId++}`
    const item: QueueItem = { localId, filePath: '', state: 'failed', message, retakeOnly: true }
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

  /** Photos not yet safely on the server, including a scheduled 503 resend. */
  pendingCount(): number {
    return (
      this.list.filter((i) => i.state === 'waiting' || i.state === 'uploading' || i.state === 'failed').length +
      this.resends
    )
  }

  retry(localId: string): void {
    if (this.stopped !== null || this.paused?.localId !== localId) return
    const item = this.list.find((i) => i.localId === localId)
    if (!item || item.state !== 'failed' || item.retakeOnly) return
    item.state = 'waiting'
    item.message = undefined
    this.paused = null
    this.emit()
    void this.pump()
  }

  /** 重拍这张: the new photo takes the paused item's place, so upload order stays shooting order. */
  replaceFile(localId: string, filePath: string): void {
    if (this.stopped !== null || this.paused?.localId !== localId) return
    const item = this.list.find((i) => i.localId === localId)
    if (!item || item.state !== 'failed') return
    item.filePath = filePath
    item.state = 'waiting'
    item.message = undefined
    item.retakeOnly = undefined
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
    this.resends = 0
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
        // Strictly in order: the first item not yet uploaded decides what happens next.
        const item = this.list.find((i) => i.state === 'waiting' || i.state === 'failed')
        if (!item) break
        if (item.state === 'failed') {
          this.paused = { localId: item.localId, message: item.message ?? '' }
          this.emit()
          break
        }
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
    this.resends++
    const t = setTimeout(() => {
      this.timers.delete(t)
      if (this.disposed) return
      this.uploader(filePath)
        .catch((e) => console.warn('silent re-upload failed', e))
        .finally(() => {
          this.resends = Math.max(0, this.resends - 1)
          this.emit()
        })
    }, RESEND_DELAY_MS)
    this.timers.add(t)
  }
}

