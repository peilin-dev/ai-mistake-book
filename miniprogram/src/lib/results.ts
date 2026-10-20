import type { QuestionResultOut } from './types'

export const NO_ANSWER_KEY_BANNER = '本次没有答案卷，答案由 AI 判断'

/** "对/错/没判出" for a question row. */
export function verdictText(q: Pick<QuestionResultOut, 'is_correct'>): string {
  if (q.is_correct === null) return '没判出'
  return q.is_correct ? '对' : '错'
}

/** "2 / 4 分", or "2 分" when the full mark is unknown, or "" without a score. */
export function scoreText(q: Pick<QuestionResultOut, 'score' | 'max_score'>): string {
  if (q.score === null) return ''
  return q.max_score !== null ? `${q.score} / ${q.max_score} 分` : `${q.score} 分`
}
