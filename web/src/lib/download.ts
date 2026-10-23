import { request } from './api'

export type ExportKind = 'lecture' | 'class_students' | 'practice'

export interface MeOut {
  id: number
  display_name: string | null
  last_subject: string | null
}

interface ExportOut {
  url: string
  filename: string
}

/** Ask the server for a PDF, fetch the signed link and save it through a download link. */
export async function exportAndDownload(
  assignmentId: number,
  kind: ExportKind,
  includeAnswers?: boolean,
): Promise<void> {
  const body: Record<string, unknown> = { kind }
  // Only the practice sheet carries the answers switch.
  if (includeAnswers !== undefined) body.include_answers = includeAnswers
  const out = await request<ExportOut>('POST', `/api/assignments/${assignmentId}/exports`, body)
  // The signature in the url is the auth: no Authorization header.
  const res = await fetch(out.url)
  if (!res.ok) throw new TypeError('download failed')
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = out.filename
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(href), 10000)
}

/** True when the practice sheet exists and is finished (404 or any other status means no). */
export async function practiceReady(assignmentId: number): Promise<boolean> {
  try {
    const p = await request<{ status: string }>('GET', `/api/assignments/${assignmentId}/practice`)
    return p.status === 'done'
  } catch (e) {
    if ((e as { status?: number } | null)?.status === 404) return false
    throw e
  }
}

export function needsSignature(me: { display_name: string | null }): boolean {
  return !me.display_name || !me.display_name.trim()
}

export const NAME_MAX = 32
