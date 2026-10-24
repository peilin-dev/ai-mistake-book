export interface SubjectOption {
  value: string
  label: string
}

const PRIMARY: SubjectOption[] = [
  { value: 'chinese', label: '语文' },
  { value: 'math', label: '数学' },
  { value: 'english', label: '英语' },
  { value: 'science', label: '科学' },
  { value: 'politics', label: '道德与法治' },
]

const SECONDARY_EXTRA: SubjectOption[] = [
  { value: 'physics', label: '物理' },
  { value: 'chemistry', label: '化学' },
  { value: 'biology', label: '生物' },
  { value: 'history', label: '历史' },
  { value: 'geography', label: '地理' },
]

export function subjectsForGrade(grade: number): SubjectOption[] {
  return grade >= 7 ? [...PRIMARY, ...SECONDARY_EXTRA] : [...PRIMARY]
}
