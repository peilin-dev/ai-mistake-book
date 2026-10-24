export interface QuestionResult {
  id: number
  page_id: number
  question_no: string
  question_text: string | null
  student_answer: string | null
  correct_answer: string | null
  subject?: string
  question_type?: string | null
  is_subjective?: boolean
  error_reason?: string | null
  scoring_basis?: string | null
  strengths?: string | null
  guidance?: string | null
  is_correct: boolean
  score: number
  max_score: number | null
  crop_url: string | null
  image_url?: string | null
  student_name?: string | null
  reason?: string
  needs_review?: boolean
  reviewed?: boolean
}
export interface Submission {
  id: number
  student_id: number
  student_name: string
  total_score: number
  needs_review_count: number
}
export const reviewReason = (reason?: string) =>
  ({
    student_uncertain: '请核对学生归属',
    low_confidence: '识别把握不足，请核对',
    answer_mismatch: '答案存在分歧，请核对',
  })[reason ?? ''] ?? '请核对作答与分数'
export function scoreError(value: string, max: number | null) {
  const n = Number(value)
  return value.trim() === '' ||
    !Number.isFinite(n) ||
    n < 0 ||
    (max !== null && n > max)
    ? `分数应为 0${max === null ? ' 以上' : `–${max}`} 的数字`
    : ''
}
