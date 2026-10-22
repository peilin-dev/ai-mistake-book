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
