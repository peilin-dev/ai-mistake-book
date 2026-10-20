import type { ProgressOut, SubmissionOut } from './types'

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
