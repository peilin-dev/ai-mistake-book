/** Shapes and helpers shared by the home and overview pages (and later the projector page). */

export interface ClassOut {
  id: number
  name: string
  grade: number
}

export interface AssignmentOut {
  id: number
  class_id: number
  subject: string
  title: string
  // The API does not return a date yet; shown only when the backend adds it.
  created_at?: string | null
}

export interface QuestionStat {
  question_no: string
  knowledge_point: string | null
  wrong_count: number
  student_count: number
  answered_count: number
  accuracy: number | null
  top_wrong_answer: string | null
  is_subjective: boolean
}

export interface Analytics {
  counted_students: number
  roster_size: number
  average_score: number | null
  average_ratio: number | null
  pass_rate: number | null
  pending_review: number
  pages_not_counted: number
  questions: QuestionStat[]
}

export type Heat = 'hot' | 'warm' | 'cool' | 'none'

const SUBJECTS: Record<string, string> = {
  chinese: '语文', math: '数学', english: '英语', science: '科学', politics: '道德与法治',
  physics: '物理', chemistry: '化学', biology: '生物', history: '历史', geography: '地理', other: '其他',
}

export function subjectLabel(value: string): string {
  return SUBJECTS[value] ?? value
}

/** wrong_count / student_count; null when nobody has a row for the question. */
export function errorRate(q: { wrong_count: number; student_count: number }): number | null {
  return q.student_count > 0 ? q.wrong_count / q.student_count : null
}

export function heatLevel(rate: number | null): Heat {
  if (rate === null) return 'none'
  if (rate >= 0.4) return 'hot'
  if (rate >= 0.2) return 'warm'
  return 'cool'
}

export function pendingHint(pending: number): string | null {
  return pending > 0 ? `还有 ${pending} 项没复核，统计可能变化，请在手机上复核` : null
}

/** Same formatting as the mini program: 0.714 -> "71%"; null -> "—". */
export function percent(x: number | null | undefined): string {
  return x === null || x === undefined ? '—' : `${Math.round(x * 100)}%`
}

/** At most one decimal; null -> "—". */
export function avgText(x: number | null | undefined): string {
  return x === null || x === undefined ? '—' : String(Math.round(x * 10) / 10)
}

/** "2026-10-23" from an API timestamp (UTC, stored naive), or '' when missing. */
export function dateText(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z')
  if (Number.isNaN(d.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
