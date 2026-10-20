import type { SubjectOption } from './subjects'

/** Last-used subject if this grade offers it, otherwise the first option. */
export function defaultSubject(
  subjects: SubjectOption[],
  lastSubject: string | null | undefined,
): string {
  if (lastSubject && subjects.some((s) => s.value === lastSubject)) return lastSubject
  return subjects[0].value
}

/** "MM-DD 作业" in local time. */
export function defaultAssignmentTitle(date: Date): string {
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  return `${mm}-${dd} 作业`
}
