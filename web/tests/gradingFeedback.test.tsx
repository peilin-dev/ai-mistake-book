import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import GradingFeedback from '../src/components/GradingFeedback'
import type { QuestionResult } from '../src/lib/results'

afterEach(cleanup)
const question: QuestionResult = {
  id: 1, page_id: 1, question_no: '1', question_text: '求长度',
  student_answer: '3', correct_answer: '3厘米', is_correct: false,
  score: 2, max_score: 3, crop_url: null,
}
it('shows evidence, specific error, strengths and actionable guidance', () => {
  render(<GradingFeedback question={{ ...question,
    scoring_basis: '计算2分，单位1分', error_reason: '遗漏厘米，扣1分',
    strengths: '3×1=3，列式正确', guidance: '在结果后补写单位', reviewed: true,
  }} />)
  for (const text of ['计算2分，单位1分', '遗漏厘米，扣1分', '3×1=3，列式正确', '在结果后补写单位']) {
    expect(screen.getByText(text)).toBeTruthy()
  }
  expect(screen.getByText(/分数以当前成绩为准/)).toBeTruthy()
})
it('does not invent feedback for legacy records', () => {
  render(<GradingFeedback question={question} />)
  expect(screen.getAllByText(/旧记录不会自动补写/)).toHaveLength(3)
})
