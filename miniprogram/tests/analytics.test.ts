import { describe, expect, it } from 'vitest'
import { AI_LABEL, historyLine, needsSignature, overviewNotices, percent, questionLine } from '../src/lib/analytics'
import type { AnalyticsOut, HistoryItem, QuestionStatOut } from '../src/lib/types'

const base: AnalyticsOut = {
  counted_students: 30,
  roster_size: 32,
  average_score: 80,
  average_ratio: 0.8,
  pass_rate: 0.9,
  pending_review: 0,
  pages_not_counted: 0,
  questions: [],
  weak_points: [],
  attention: [],
}

const q = (o: Partial<QuestionStatOut> = {}): QuestionStatOut => ({
  question_no: '3',
  knowledge_point: null,
  wrong_count: 5,
  answered_count: 10,
  accuracy: 0.5,
  top_wrong_answer: '13',
  is_subjective: false,
  ...o,
})

describe('percent', () => {
  it('rounds to a whole percent', () => {
    expect(percent(0.714)).toBe('71%')
    expect(percent(0.995)).toBe('100%')
    expect(percent(0)).toBe('0%')
  })
  it('shows a dash for null', () => {
    expect(percent(null)).toBe('—')
  })
})

describe('overviewNotices', () => {
  it('is empty when nothing to flag', () => {
    expect(overviewNotices(base)).toEqual([])
  })
  it('flags pending review with a review action', () => {
    expect(overviewNotices({ ...base, pending_review: 3 })).toEqual([
      { text: '还有 3 题待复核，统计可能不准', action: 'review' },
    ])
  })
  it('flags uncounted pages, review first', () => {
    expect(overviewNotices({ ...base, pending_review: 1, pages_not_counted: 2 })).toEqual([
      { text: '还有 1 题待复核，统计可能不准', action: 'review' },
      { text: '还有 2 张卷子没批完或没认出学生，统计暂未包含', action: null },
    ])
  })
})

describe('questionLine', () => {
  it('shows accuracy and the most common wrong answer', () => {
    expect(questionLine(q())).toBe('正确率 50% · 最常见错答「13」')
  })
  it('stops at accuracy for subjective questions', () => {
    expect(questionLine(q({ is_subjective: true }))).toBe('正确率 50%')
  })
  it('stops at accuracy without a wrong answer, and handles null accuracy', () => {
    expect(questionLine(q({ top_wrong_answer: null }))).toBe('正确率 50%')
    expect(questionLine(q({ accuracy: null, top_wrong_answer: null }))).toBe('正确率 —')
  })
})

describe('historyLine', () => {
  const h = (o: Partial<HistoryItem> = {}): HistoryItem => ({
    assignment_id: 1,
    title: '10-22 作业',
    created_at: '2026-10-22T01:00:00',
    score: 9,
    max_score: 14,
    ratio: 9 / 14,
    ...o,
  })
  it('joins title, score and rounded percent', () => {
    expect(historyLine(h())).toBe('10-22 作业　9 / 14 分（64%）')
  })
  it('shows only the score when there is no full mark', () => {
    expect(historyLine(h({ max_score: 0, ratio: null }))).toBe('10-22 作业　9 分')
  })
})

describe('needsSignature', () => {
  it('is true for null or blank names', () => {
    expect(needsSignature({ display_name: null })).toBe(true)
    expect(needsSignature({ display_name: '  ' })).toBe(true)
  })
  it('is false once a name is set', () => {
    expect(needsSignature({ display_name: '王老师' })).toBe(false)
  })
})

describe('AI_LABEL', () => {
  it('is the fixed label', () => {
    expect(AI_LABEL).toBe('AI 推测')
  })
})
