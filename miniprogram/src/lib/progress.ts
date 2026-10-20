import type { PageOut, AssignmentOut, ProgressOut, SubmissionOut } from './types'

export function isFinished(progress: ProgressOut): boolean {
  return progress.total > 0 && progress.queued + progress.processing === 0
}

export function progressText(
  p: ProgressOut,
  submissions: SubmissionOut[],
  rosterSize: number,
): { pages: string; students: string } {
  return {
    pages: `已批 ${p.done}/${p.total} 张`,
    students: `已出成绩 ${submissions.length}/${rosterSize} 人`,
  }
}

export function assignmentHints(a: AssignmentOut, rosterSize: number): string[] {
  const hints: string[] = []
  if (rosterSize === 0) hints.push('这个班还没有名单，先导入名单才能认出学生')
  if (!a.has_answer_key) hints.push('本次没有答案卷，答案由 AI 判断')
  return hints
}

export type AnswerKeyAction = 'shoot' | 'confirm' | 'confirmed'

/** What the answer-key area on the assignment page offers for a given status. */
export function answerKeyAction(status: string): AnswerKeyAction {
  if (status === 'confirmed') return 'confirmed'
  if (status === 'pending') return 'confirm'
  return 'shoot'
}

/** Which optional bottom buttons to show: review count (0 = hidden) and results. */
export function bottomActions(
  p: ProgressOut,
  submissionCount: number,
): { review: number; results: boolean } {
  return { review: p.needs_review > 0 ? p.needs_review : 0, results: submissionCount > 0 }
}
/** Failed pages first (easy to find in a long list), then the rest in seq order. */
export function orderPages(pages: PageOut[]): PageOut[] {
  const bySeq = [...pages].sort((a, b) => a.seq - b.seq)
  return [...bySeq.filter((p) => p.status === 'failed'), ...bySeq.filter((p) => p.status !== 'failed')]
}