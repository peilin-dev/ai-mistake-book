import Taro from '@tarojs/taro'
import { ApiError, request } from './api'
import { API_BASE } from './config'
import { errorText } from './messages'

export type ExportKind = 'lecture' | 'student' | 'class_students'

export interface MeOut {
  id: number
  display_name: string | null
  last_subject: string | null
}

interface ExportOut {
  url: string
  filename: string
}

/** Ask the server for a PDF, download it and open it (the menu lets the teacher forward it). */
export async function exportPdf(
  assignmentId: number,
  kind: ExportKind,
  submissionId?: number,
): Promise<void> {
  const out = await request<ExportOut>('POST', `/api/assignments/${assignmentId}/exports`, {
    kind,
    submission_id: submissionId ?? null,
  })
  const res = await Taro.downloadFile({ url: `${API_BASE}${out.url}` })
  if (res.statusCode !== 200 || !res.tempFilePath) {
    throw new Error('downloadFile:fail bad status')
  }
  await Taro.openDocument({ filePath: res.tempFilePath, fileType: 'pdf', showMenu: true })
}

/** 409 carries a readable reason ("全对，没有错题"); everything else uses the shared texts. */
export function exportErrorText(e: unknown): string {
  if (e instanceof ApiError && e.status === 409 && e.detail) return e.detail
  const msg = (e as { errMsg?: unknown } | null | undefined)?.errMsg
  if (typeof msg === 'string' && msg.includes('downloadFile:fail')) return '网络不太好，请稍后再试'
  if (e instanceof Error && e.message.includes('downloadFile:fail')) return '网络不太好，请稍后再试'
  return errorText(e)
}

export function loadMe(): Promise<MeOut> {
  return request<MeOut>('GET', '/api/me')
}

export function saveSignature(name: string): Promise<MeOut> {
  return request<MeOut>('PATCH', '/api/me', { display_name: name.trim() })
}
