import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import PaperComparison from '../src/components/PaperComparison'
import type { QuestionResult } from '../src/lib/results'

afterEach(cleanup)
const question: QuestionResult = { id: 1, page_id: 10, question_no: '1', question_text: '求面积', student_answer: '12', correct_answer: '16', score: 2, max_score: 4, is_correct: false, subject: 'math', question_type: 'calculation', crop_url: '/crop.png', scoring_steps: [{ criterion: '列式', score: 2, max_score: 2, reason: '列式正确' }, { criterion: '计算', score: 0, max_score: 2, reason: '乘法出错，扣2分' }] }
it('compares the selected original page and question with partial credit', () => {
  render(<PaperComparison questions={[question, { ...question, id: 2, page_id: 11, question_no: '2', student_answer: '第二页作答' }]} pages={[{ page_id: 10, seq: 1, image_url: '/one.png' }, { page_id: 11, seq: 2, image_url: '/two.png' }]} onSaved={vi.fn()} />)
  expect(screen.getByRole('img').getAttribute('src')).toBe('/one.png')
  expect(screen.getByText(/部分得分/)).toBeTruthy()
  expect(screen.getByText('乘法出错，扣2分')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '只看本题' }))
  expect(screen.getByRole('img').getAttribute('src')).toBe('/crop.png')
  fireEvent.change(screen.getByLabelText('选择原卷页'), { target: { value: '11' } })
  expect(screen.getByRole('img').getAttribute('src')).toBe('/two.png')
  expect(screen.getByText('第二页作答')).toBeTruthy()
})
it('keeps AI step awards identifiable after a teacher correction', () => {
  render(<PaperComparison questions={[{ ...question, reviewed: true, model_score: 2, score: 3 }]} onSaved={vi.fn()} />)
  expect(screen.getByText(/AI 原始得分 2/)).toBeTruthy()
  expect(screen.getByText(/AI 原始步骤评分/)).toBeTruthy()
  expect(screen.getByText(/原卷暂不可用/)).toBeTruthy()
})
