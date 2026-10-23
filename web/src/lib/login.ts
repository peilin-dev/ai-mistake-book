import { request } from './api'

export interface Ticket {
  ticket: string
  poll_key: string
  pair_code: string
  qr_png: string
  expires_in: number
}

export type PollStatus = 'pending' | 'scanned' | 'confirmed' | 'cancelled' | 'expired'

export interface PollResult {
  status: PollStatus
  expires_in: number
  token: string | null
  teacher: { id: number; display_name: string } | null
}

/** WeChat returns a JPEG although the field is named qr_png; sniff the magic bytes. */
export function qrDataUrl(b64: string): string {
  let mime = 'image/png'
  try {
    const head = atob(b64.slice(0, 8))
    if (head.charCodeAt(0) === 0xff && head.charCodeAt(1) === 0xd8) mime = 'image/jpeg'
  } catch {
    /* keep png */
  }
  return `data:${mime};base64,${b64}`
}

export function createTicket(): Promise<Ticket> {
  return request<Ticket>('POST', '/api/web-login/tickets')
}

export function pollOnce(t: Ticket): Promise<PollResult> {
  return request<PollResult>(
    'GET',
    `/api/web-login/tickets/${encodeURIComponent(t.ticket)}?poll_key=${encodeURIComponent(t.poll_key)}`,
  )
}

export function startPolling(
  t: Ticket,
  onState: (s: 'pending' | 'scanned' | 'expired' | 'cancelled') => void,
  onToken: (token: string) => void,
  intervalMs = 2000,
): () => void {
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let last: string | null = null

  const tick = async () => {
    try {
      const r = await pollOnce(t)
      if (stopped) return
      if (r.status === 'confirmed') {
        stopped = true
        if (r.token) onToken(r.token)
        else onState('expired')
        return
      }
      if (r.status !== last) {
        last = r.status
        onState(r.status)
      }
      if (r.status === 'expired' || r.status === 'cancelled') {
        stopped = true
        return
      }
    } catch {
      if (stopped) return
      /* transient error: keep polling */
    }
    timer = setTimeout(tick, intervalMs)
  }
  timer = setTimeout(tick, intervalMs)
  return () => {
    stopped = true
    if (timer) clearTimeout(timer)
  }
}