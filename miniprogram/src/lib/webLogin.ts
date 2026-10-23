import { ApiError, request } from './api'
import { errorText } from './messages'

const TICKET_RE = /^[A-Za-z0-9_-]{16}$/

/** The mini program code's scene arrives URL-encoded; only a 16-char token_urlsafe id is accepted. */
export function ticketFromScene(scene: string | undefined): string | null {
  if (!scene) return null
  let decoded: string
  try {
    decoded = decodeURIComponent(scene)
  } catch {
    return null
  }
  return TICKET_RE.test(decoded) ? decoded : null
}

const base = (ticket: string) => `/api/web-login/tickets/${ticket}`

export function scanTicket(ticket: string): Promise<{ pair_code: string }> {
  return request<{ pair_code: string }>('POST', `${base(ticket)}:scan`)
}

export async function confirmTicket(ticket: string): Promise<void> {
  await request('POST', `${base(ticket)}:confirm`)
}

export async function cancelTicket(ticket: string): Promise<void> {
  await request('POST', `${base(ticket)}:cancel`)
}

export function webLoginErrorText(e: unknown): string {
  if (e instanceof ApiError && e.status === 410) return '二维码已过期，请在电脑上刷新'
  if (e instanceof ApiError && e.status === 409) return '这个二维码已经被使用，请在电脑上刷新'
  return errorText(e)
}
