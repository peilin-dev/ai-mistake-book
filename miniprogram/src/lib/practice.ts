import type { PracticeItemOut, PracticePaperOut } from './types'

export const PARTIAL_TEXT = '部分题目没出成，可以重新生成'
export const FAILED_TEXT = '这次没出成题，请稍后重试'

export function progressText(p: PracticePaperOut): string {
  if (p.status === 'queued' && p.sources_done === 0) return '正在出题…'
  return `正在出题…（已完成 ${p.sources_done} / ${p.sources_total} 道源题）`
}

export function isWorking(p: PracticePaperOut): boolean {
  return p.status === 'queued' || p.status === 'running' || p.items.some((i) => i.replacing)
}

export function sourceLabel(item: PracticeItemOut): string {
  const kp = (item.knowledge_point ?? '').trim()
  return `第 ${item.source_no} 题的同类题${kp ? ` · ${kp}` : ''}`
}

export function optionLetter(i: number): string {
  return String.fromCharCode(65 + i)
}

/** generated_at is a naive-UTC ISO string; show it in the phone's local time ("10月22日 16:30"). */
export function generatedAtText(iso: string | null): string {
  if (!iso) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(iso)
  if (!m) return ''
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] ?? 0)))
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hh}:${mm}`
}

export const REPLACE_FAILED_TEXT = '没换成，原题保留'

/** The asked-to-replace item that came back not replacing and is flagged as failed, if any. */
export function failedReplace(asked: number[], p: PracticePaperOut): number | null {
  const failed = p.last_replace_failed_item
  if (failed === null || !asked.includes(failed)) return null
  const it = p.items.find((i) => i.id === failed)
  return it && !it.replacing ? failed : null
}
