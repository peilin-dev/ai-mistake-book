import { ApiError } from './api'

export type FailAction = 'retake' | 'retry'

const RETRY_REASONS = ['model_unavailable', 'internal_error']

export function failReasonText(reason: string | null): string {
  switch (reason) {
    case 'unreadable':
      return '看不清，请重拍这张'
    case 'model_unavailable':
    case 'internal_error':
      return '批改服务暂时出错，点重试'
    default:
      // model_output_invalid, unknown, null
      return '这张没批出来，请重拍'
  }
}

export function failReasonAction(reason: string | null): FailAction | null {
  if (reason === null) return null
  return RETRY_REASONS.includes(reason) ? 'retry' : 'retake'
}

function isNetworkError(e: unknown): boolean {
  if (e instanceof ApiError) return e.status === 0
  const msg =
    e instanceof Error ? e.message : (e as { errMsg?: unknown } | null | undefined)?.errMsg
  return typeof msg === 'string' && msg.includes('request:fail')
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError && [409, 429, 503].includes(e.status) && e.detail) return e.detail
  if (isNetworkError(e)) return '网络不太好，请稍后再试'
  return '出了点问题，请稍后再试'
}
