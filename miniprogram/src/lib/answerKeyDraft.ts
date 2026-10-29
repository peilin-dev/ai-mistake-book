import type { AnswerKeyItem } from './types'

// A camera preview belongs to one assignment and is consumed by its editor.
let draft: { assignmentId: number; items: AnswerKeyItem[] } | undefined
export function setAnswerKeyDraft(assignmentId: number, items: AnswerKeyItem[]) {
  draft = { assignmentId, items }
}
export function takeAnswerKeyDraft(assignmentId: number): AnswerKeyItem[] | undefined {
  const current = draft
  draft = undefined
  return current?.assignmentId === assignmentId ? current.items : undefined
}
