import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/lib/api', () => ({
  request: vi.fn(),
  errorText: (e: unknown) => (e instanceof Error ? e.message : 'x'),
  ApiError: class extends Error {},
  setOnUnauthorized: () => {},
}))
vi.mock('../src/components/Header', () => ({ default: () => null }))

import { request } from '../src/lib/api'
import Question from '../src/pages/Question'

const req = request as unknown as ReturnType<typeof vi.fn>
afterEach(() => { cleanup(); req.mockReset() })

const detail = {
  question_no: '2', question_text: '3+4=?', correct_answer: '7', is_subjective: false,
  knowledge_point: '加法', wrong_count: 3, student_count: 4, answered_count: 4,
  groups: [
    { answer: '6', key: 'k6', count: 2, students: [
      { student_id: 1, student_name: '张三', submission_id: 11, score: 0, max_score: 2 },
      { student_id: 2, student_name: '李四', submission_id: 12, score: 0, max_score: 2 },
    ] },
    { answer: '8', key: 'k8', count: 1, students: [
      { student_id: 3, student_name: '张三', submission_id: 13, score: 0, max_score: 2 },
    ] },
  ],
  score_buckets: [],
  crops: [
    { student_name: '张三', submission_id: 11, crop_url: '/api/files/a' },
    { student_name: '李四', submission_id: 12, crop_url: '/api/files/b' },
    { student_name: '张三', submission_id: 13, crop_url: '/api/files/c' },
  ],
}
const analytics = {
  counted_students: 4, roster_size: 4, average_score: 5, average_ratio: 0.5, pass_rate: 0.5,
  pending_review: 0, pages_not_counted: 0,
  questions: ['1', '2', '3'].map((n) => ({ question_no: n, knowledge_point: null, wrong_count: 1,
    student_count: 4, answered_count: 4, accuracy: 0.5, top_wrong_answer: null, is_subjective: false })),
}

function mock() {
  req.mockImplementation((m: string, path: string) => {
    if (path.endsWith('/analytics')) return Promise.resolve(analytics)
    if (path.endsWith('/causes')) return Promise.resolve({ causes: { k6: '把加数看错了' } })
    if (path.includes('/analytics/questions/')) return Promise.resolve(detail)
    return Promise.reject(new Error('unexpected ' + m + path))
  })
}

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>
}
function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/a/5/q/2']}>
      <Where />
      <Routes><Route path="/a/:assignmentId/q/:questionNo" element={<Question />} /></Routes>
    </MemoryRouter>,
  )
}

describe('question page', () => {
  it('shows the headline with count and percent', async () => {
    mock()
    renderPage()
    await waitFor(() => expect(document.body.textContent).toContain('第 2 题　错了 3 人（75%）'))
    expect(document.body.textContent).toContain('写成 6，2 人')
    await waitFor(() => expect(document.body.textContent).toContain('把加数看错了'))
  })

  it('never renders student names', async () => {
    mock()
    renderPage()
    await waitFor(() => expect(document.body.textContent).toContain('把加数看错了'))
    expect(document.querySelectorAll('img').length).toBeGreaterThan(0)
    expect(document.body.textContent).not.toMatch(/张三|李四/)
    for (const el of Array.from(document.querySelectorAll('*'))) {
      for (const attr of Array.from(el.attributes)) {
        expect(attr.value).not.toMatch(/张三|李四/)
      }
    }
  })

  it('arrow keys navigate', async () => {
    mock()
    renderPage()
    await waitFor(() => expect(document.body.textContent).toContain('把加数看错了'))
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByTestId('where').textContent).toBe('/a/5/q/3')
  })

  it('arrow left goes to the previous question', async () => {
    mock()
    renderPage()
    await waitFor(() => expect(document.body.textContent).toContain('第 2 题'))
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByTestId('where').textContent).toBe('/a/5/q/1')
  })
})
