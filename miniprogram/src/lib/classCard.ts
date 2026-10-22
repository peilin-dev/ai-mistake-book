import { isFinished } from './progress'
import type { AssignmentOut, ProgressOut } from './types'

export type Tone = 'warn' | 'ok' | 'busy' | 'gray'

/** Status pill for a class card on the home page, from its latest assignment. */
export function classCardStatus(
  latest: AssignmentOut | null,
  progress: ProgressOut | null,
): { text: string; tone: Tone } {
  if (!latest) return { text: '还没有作业', tone: 'gray' }
  if (!progress) return { text: '', tone: 'gray' }
  if (progress.total === 0) return { text: '还没拍卷', tone: 'gray' }
  if (progress.needs_review > 0) return { text: `${progress.needs_review} 题待复核`, tone: 'warn' }
  if (!isFinished(progress)) return { text: `批改中 ${progress.done}/${progress.total}`, tone: 'busy' }
  return { text: '全部完成', tone: 'ok' }
}

/** Share of photographed pages that finished grading (failed ones too), or null when there are none. */
export function gradedPercent(progress: ProgressOut | null): number | null {
  if (!progress || progress.total === 0) return null
  return Math.round(((progress.done + progress.failed) / progress.total) * 100)
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

/** "10月22日 · 周四" for the home page header. */
export function todayLine(d: Date): string {
  return `${d.getMonth() + 1}月${d.getDate()}日 · 周${WEEKDAYS[d.getDay()]}`
}
