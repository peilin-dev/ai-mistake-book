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

/** What a failed page offers; one with no recorded reason is re-shot. */
export function failReasonAction(reason: string | null): FailAction {
  return reason !== null && RETRY_REASONS.includes(reason) ? 'retry' : 'retake'
}

const CJK = /[一-鿿]/

export function isNetworkError(e: unknown): boolean {
  if (e instanceof ApiError) return e.status === 0
  const msg =
    e instanceof Error ? e.message : (e as { errMsg?: unknown } | null | undefined)?.errMsg
  return typeof msg === 'string' && msg.includes('request:fail')
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError && [409, 429, 503].includes(e.status) && e.detail) return e.detail
  // Answer-key errors ("未识别到题目", "答案卷识别失败，请重拍"); validation noise stays hidden.
  if (e instanceof ApiError && [422, 502].includes(e.status) && CJK.test(e.detail) && !/^[[{]/.test(e.detail)) {
    return e.detail
  }
  if (e instanceof ApiError && e.status === 401) return '登录已过期，请重新打开小程序'
  if (e instanceof ApiError && e.status === 413) return '照片太大了，请重拍这张'
  if (e instanceof ApiError && e.status === 415) return '这不是照片，请重拍这张'
  if (isNetworkError(e)) return '网络不太好，请稍后再试'
  return '出了点问题，请稍后再试'
}


export function pageStatusText(status: string): string {
  switch (status) {
    case 'queued':
      return '排队中'
    case 'processing':
      return '批改中'
    case 'done':
      return '已批完'
    default:
      return '没批成'
  }
}