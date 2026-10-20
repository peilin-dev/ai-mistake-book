import { describe, expect, it } from 'vitest'
import { orderPages, answerKeyAction, assignmentHints, bottomActions, isFinished, progressText } from '../src/lib/progress'
import type { PageOut, AssignmentOut, ProgressOut, SubmissionOut } from '../src/lib/types'

const p = (o: Partial<ProgressOut>): ProgressOut => ({
  total: 0, queued: 0, processing: 0, done: 0, failed: 0, needs_review: 0, ...o,
})

describe('isFinished', () => {
  it('false when nothing uploaded', () => expect(isFinished(p({}))).toBe(false))
  it('false while queued or processing', () => {
    expect(isFinished(p({ total: 3, queued: 1, done: 2 }))).toBe(false)
    expect(isFinished(p({ total: 3, processing: 1, done: 2 }))).toBe(false)
  })
  it('true when all done or failed', () => {
    expect(isFinished(p({ total: 3, done: 2, failed: 1 }))).toBe(true)
  })
})

describe('progressText', () => {
  it('formats pages and students', () => {
    const subs = [{ id: 1 }, { id: 2 }] as SubmissionOut[]
    expect(progressText(p({ total: 5, done: 3, failed: 1, queued: 1 }), subs, 40)).toEqual({
      pages: '已批 3/5 张',
      students: '已出成绩 2/40 人',
    })
  })
  it('zero state', () => {
    expect(progressText(p({}), [], 0)).toEqual({ pages: '已批 0/0 张', students: '已出成绩 0/0 人' })
  })
})

describe('assignmentHints', () => {
  const a = (o: Partial<AssignmentOut>): AssignmentOut => ({
    id: 1, class_id: 1, subject: 'math', title: 't', answer_key_status: 'confirmed', has_answer_key: true, ...o,
  })
  it('rosterEmptyHint', () => {
    expect(assignmentHints(a({}), 0)).toEqual(['这个班还没有名单，先导入名单才能认出学生'])
  })
  it('noAnswerKeyHint', () => {
    expect(assignmentHints(a({ has_answer_key: false, answer_key_status: 'none' }), 30)).toEqual([
      '本次没有答案卷，答案由 AI 判断',
    ])
  })
  it('both hints, roster first', () => {
    expect(assignmentHints(a({ has_answer_key: false }), 0)).toHaveLength(2)
  })
  it('no hints when all good', () => expect(assignmentHints(a({}), 30)).toEqual([]))
})

describe('answerKeyAction', () => {
  it('maps status to action', () => {
    expect(answerKeyAction('none')).toBe('shoot')
    expect(answerKeyAction('pending')).toBe('confirm')
    expect(answerKeyAction('confirmed')).toBe('confirmed')
  })
})

describe('bottomActions', () => {
  it('shows review and results only when relevant', () => {
    expect(bottomActions(p({}), 0)).toEqual({ review: 0, results: false })
    expect(bottomActions(p({ total: 3, done: 3, needs_review: 2 }), 1)).toEqual({ review: 2, results: true })
  })
})
describe('orderPages', () => {
  it('failed first, then the rest by seq', () => {
    const mk = (seq: number, status: string) => ({ page_id: seq, seq, status }) as PageOut
    const out = orderPages([mk(1, 'done'), mk(2, 'failed'), mk(3, 'queued'), mk(4, 'failed')])
    expect(out.map((x) => x.seq)).toEqual([2, 4, 1, 3])
  })
})