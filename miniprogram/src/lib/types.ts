// Field names mirror the backend JSON (backend/app/*/router.py).

export type AnswerKeyStatus = string
export type PageStatus = 'queued' | 'processing' | 'done' | 'failed'
export type FailReason =
  | 'unreadable'
  | 'model_output_invalid'
  | 'model_unavailable'
  | 'internal_error'
  | string

export interface ClassOut {
  id: number
  name: string
  grade: number
}

export interface StudentOut {
  id: number
  name: string
  student_no: string | null
}

export interface AssignmentOut {
  id: number
  class_id: number
  subject: string
  title: string
  answer_key_status: AnswerKeyStatus
  has_answer_key: boolean
}

export interface PageOut {
  page_id: number
  seq: number
  status: PageStatus
  fail_reason: FailReason | null
  student_id: number | null
  student_name: string | null
  recognized_name: string | null
}

export interface ProgressOut {
  total: number
  queued: number
  processing: number
  done: number
  failed: number
  needs_review: number
}

export interface QuestionResultOut {
  id: number
  question_no: string
  question_text: string
  student_answer: string | null
  correct_answer: string | null
  is_correct: boolean | null
  score: number | null
  max_score: number | null
  confidence: number | null
  page_id: number
  needs_review: boolean
  reviewed: boolean
  model_is_correct: boolean | null
  model_score: number | null
  crop_url: string | null
  /** false: the answer was judged by the AI (no confirmed answer key). */
  answer_verified?: boolean
}

export interface SubmissionOut {
  id: number
  assignment_id?: number
  student_id: number
  student_name: string
  total_score: number
  needs_review_count: number
  /** Present on GET /api/submissions/{id} only. */
  questions?: QuestionResultOut[]
}

export interface ReviewQuestion {
  id: number
  question_no: string
  question_text: string
  student_answer: string | null
  correct_answer: string | null
  is_correct: boolean | null
  score: number | null
  max_score: number | null
  confidence: number | null
  student_name: string | null
  reason: 'student_uncertain' | 'low_confidence' | 'answer_mismatch'
  crop_url: string | null
  page_id: number
  recognized_name: string | null
  image_url: string | null
}

export interface ReviewOut {
  pages_unassigned: { page_id: number; image_url: string | null; recognized_name: string | null }[]
  questions: ReviewQuestion[]
}

export interface AnswerKeyItem {
  question_no: string
  answer: string
  max_score: number | null
  is_subjective: boolean
}