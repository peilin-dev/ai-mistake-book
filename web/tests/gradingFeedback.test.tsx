import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import GradingFeedback, { feedbackSections } from '../src/components/GradingFeedback'
import type { QuestionResult } from '../src/lib/results'

afterEach(cleanup)
const question: QuestionResult = {
  id: 1, page_id: 1, question_no: '1', question_text: '求长度',
  student_answer: '3', correct_answer: '3厘米', is_correct: false,
  score: 2, max_score: 3, crop_url: null,
}
const full = { ...question, scoring_basis: '计算2分，单位1分', error_reason: '遗漏厘米，扣1分', strengths: '优美句子', guidance: '补写单位' }
it('math shows error and solution without commentary or praise', () => {
  render(<GradingFeedback question={{ ...full, subject: 'math', question_type: 'calculation', reviewed: true }} />)
  expect(screen.getByText('错因与错误步骤')).toBeTruthy()
  expect(screen.getByText('补写单位')).toBeTruthy()
  expect(screen.queryByText('优美句子')).toBeNull()
  expect(screen.getByText(/分数以当前成绩为准/)).toBeTruthy()
})
it('correct objective and math questions stay concise', () => {
  for (const subject of ['math', 'english', 'chinese', 'physics']) {
    expect(feedbackSections({ ...full, subject, score: 3, question_type: 'objective' })).toEqual([])
  }
  expect(feedbackSections({ ...full, subject: 'math', score: 3, is_subjective: true })).toEqual([])
})
it('writing keeps appreciation while reading shows answer points', () => {
  expect(feedbackSections({ ...full, subject: 'chinese', question_type: 'writing' }).map(s => s[0])).toContain('好句赏析')
  expect(feedbackSections({ ...full, subject: 'english', question_type: 'writing' }).map(s => s[0])).toContain('优秀表达')
  const reading = feedbackSections({ ...full, subject: 'chinese', question_type: 'reading' })
  expect(reading.map(s => s[0])).toContain('遗漏要点与错误')
  expect(reading.some(s => s[1] === '优美句子')).toBe(false)
})
it('uses subject specific labels and omits empty sections', () => {
  expect(feedbackSections({ ...full, subject: 'english', question_type: 'objective' })[0][0]).toBe('语法与词义错因')
  for (const subject of ['chemistry', 'biology', 'science']) expect(feedbackSections({ ...full, subject })[0][0]).toBe('知识点与得分依据')
  for (const subject of ['history', 'geography', 'politics']) expect(feedbackSections({ ...full, subject })[0][0]).toBe('得分要点')
  render(<GradingFeedback question={question} />)
  expect(screen.queryByText(/未记录/)).toBeNull()
  expect(feedbackSections({ ...question, subject: 'math', error_reason: '计算失误' })).toEqual([['错因与错误步骤', '计算失误']])
})
