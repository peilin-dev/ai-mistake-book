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
  answer_verified: boolean
  is_subjective: boolean
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

export interface WeakPoint {
  name: string
  wrong_count: number
}

export interface AttentionStudent {
  student_id: number
  student_name: string
  submission_id: number
  score: number
  max_score: number
  ratio: number
  wrong_count: number
}

export interface QuestionStatOut {
  question_no: string
  knowledge_point: string | null
  wrong_count: number
  /** everyone with a result for this question: use for headcounts */
  student_count: number
  /** those with a full mark on record: the accuracy denominator only */
  answered_count: number
  accuracy: number | null
  top_wrong_answer: string | null
  is_subjective: boolean
}

/** GET /api/assignments/{id}/analytics */
export interface AnalyticsOut {
  counted_students: number
  roster_size: number
  average_score: number | null
  average_ratio: number | null
  pass_rate: number | null
  pending_review: number
  pages_not_counted: number
  questions: QuestionStatOut[]
  weak_points: WeakPoint[]
  attention: AttentionStudent[]
}

export interface AnswerGroupStudent {
  student_id: number
  student_name: string
  submission_id: number
  score: number
  max_score: number
}

export interface AnswerGroupOut {
  answer: string
  key: string
  count: number
  students: AnswerGroupStudent[]
}

export interface ScoreBucket {
  label: string
  count: number
}

export interface QuestionCrop {
  student_name: string
  submission_id: number
  crop_url: string
}

/** GET /api/assignments/{id}/analytics/questions/{question_no} */
export interface QuestionDetailOut {
  question_no: string
  question_text: string | null
  correct_answer: string | null
  is_subjective: boolean
  knowledge_point: string | null
  wrong_count: number
  /** everyone with a result for this question: use for headcounts */
  student_count: number
  /** those with a full mark on record: the accuracy denominator only */
  answered_count: number
  groups: AnswerGroupOut[]
  score_buckets: ScoreBucket[]
  crops: QuestionCrop[]
}

/** GET /api/submissions/{id}/history items; created_at is a naive-UTC ISO string. */
export interface HistoryItem {
  assignment_id: number
  title: string
  created_at: string
  score: number
  max_score: number
  ratio: number | null
}

/** POST .../causes */
export interface CausesOut {
  causes: Record<string, string>
}

/** POST /api/submissions/{id}/summary */
export interface SummaryOut {
  summary: string | null
}

export type PracticeKind = 'choice' | 'blank' | 'judge' | 'calc'
export type PracticeStatus = 'queued' | 'running' | 'done' | 'failed'

/** One practice question inside a paper (backend ItemOut). */
export interface PracticeItemOut {
  id: number
  position: number
  source_no: string
  knowledge_point: string | null
  kind: PracticeKind | string
  stem: string
  options: string[] | null
  answer: string
  replacing: boolean
}

/** Practice paper (backend PaperOut); generated_at is a naive-UTC ISO string. */
export interface PracticePaperOut {
  id: number
  scope: 'class' | 'student'
  student_name: string | null
  status: PracticeStatus | string
  partial: boolean
  sources_total: number
  sources_done: number
  error: string | null
  generated_at: string | null
  last_replace_failed_item: number | null
  items: PracticeItemOut[]
}