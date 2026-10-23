export interface PageItem {
  page_id: number
  seq: number
  status: string
  fail_reason: string | null
  student_id: number | null
  student_name: string | null
  recognized_name: string | null
  source: string
}
export interface Progress {
  total: number
  queued: number
  processing: number
  done: number
  failed: number
  needs_review: number
}
const reasons: Record<string, string> = {
  model_unavailable: '批改服务暂不可用，可以重试',
  internal_error: '批改中断，可以重试',
  unreadable: '图片看不清，请换一张',
  no_questions: '没有识别到题目，请检查图片',
}
export function pageStatusText(p: PageItem): string {
  if (p.status === 'done') return p.student_id === null ? '待认领' : '完成'
  if (p.status === 'failed')
    return `失败：${reasons[p.fail_reason ?? ''] ?? '请检查图片或换一张'}`
  return p.status === 'processing' ? '批改中' : '排队中'
}
export const canRetry = (p: PageItem) =>
  p.status === 'failed' &&
  ['model_unavailable', 'internal_error'].includes(p.fail_reason ?? '')
