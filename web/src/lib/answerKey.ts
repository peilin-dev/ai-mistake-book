// Validation rules shared with miniprogram/src/lib/answerKey.ts.
export interface AnswerKeyItem {
  question_no: string
  answer: string
  max_score: number | null
  is_subjective: boolean
}

/** One editable line on the answer-key confirmation page. */
export interface KeyRow {
  /** Stable React key; never sent to the server. */
  key: string
  question_no: string
  answer: string
  /** Text as typed; empty means "no score printed on the key". */
  max_score: string
  is_subjective: boolean
}

let counter = 0
function nextKey(): string {
  counter += 1
  return `r${counter}`
}

export function blankRow(): KeyRow {
  return {
    key: nextKey(),
    question_no: '',
    answer: '',
    max_score: '',
    is_subjective: false,
  }
}

export function toRows(items: AnswerKeyItem[]): KeyRow[] {
  return items.map((i) => ({
    key: nextKey(),
    question_no: i.question_no,
    answer: i.answer,
    max_score: i.max_score === null ? '' : String(i.max_score),
    is_subjective: i.is_subjective,
  }))
}

function parseScore(text: string): number | null | undefined {
  const t = text.trim()
  if (t === '') return null
  const n = Number(t)
  return Number.isFinite(n) && n >= 0 ? n : undefined
}

/** Returns a message for the teacher, or null when the rows can be saved. */
export function validateRows(rows: KeyRow[]): string | null {
  if (rows.length === 0) return '还没有题目，请先加一行'
  const seen = new Set<string>()
  for (let i = 0; i < rows.length; i++) {
    const no = rows[i].question_no.trim()
    if (no === '') return `第 ${i + 1} 行没有填题号`
    if (seen.has(no)) return `题号 ${no} 重复了，请改一下`
    seen.add(no)
    if (parseScore(rows[i].max_score) === undefined)
      return `第 ${i + 1} 行的分值要填数字`
  }
  return null
}

/** Body for PUT /api/assignments/{id}/answer-key. Call validateRows first. */
export function toPutBody(rows: KeyRow[]): { items: AnswerKeyItem[] } {
  return {
    items: rows.map((r) => ({
      question_no: r.question_no.trim(),
      answer: r.answer.trim(),
      max_score: parseScore(r.max_score) ?? null,
      is_subjective: r.is_subjective,
    })),
  }
}
