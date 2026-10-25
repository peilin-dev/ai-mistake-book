import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/lib/api', () => ({
  request: vi.fn(),
  errorText: (e: unknown) => (e instanceof Error ? e.message : 'x'),
  ApiError: class extends Error {},
  setOnUnauthorized: () => {},
}))
vi.mock('../src/components/Header', () => ({ default: () => null }))

import { request } from '../src/lib/api'
import Home from '../src/pages/Home'
import Overview from '../src/pages/Overview'

const req = request as unknown as ReturnType<typeof vi.fn>
const stats = (n: number) => ({
  counted_students: n, roster_size: 10, average_score: 5, average_ratio: 0.5, pass_rate: 0.5,
  pending_review: 0, pages_not_counted: 0,
  questions: [{ question_no: '1', knowledge_point: null, wrong_count: 1, student_count: 2, answered_count: 2,
    accuracy: 0.5, top_wrong_answer: null, is_subjective: false }],
})
afterEach(() => { cleanup(); req.mockReset() })

function Nav() {
  const nav = useNavigate()
  return <button onClick={() => nav('/a/2')}>go2</button>
}
function renderOverview() {
  return render(
    <MemoryRouter initialEntries={['/a/1']}>
      <Nav />
      <Routes><Route path="/a/:assignmentId" element={<Overview />} /></Routes>
    </MemoryRouter>,
  )
}

describe('Overview states', () => {
  it('renders even when /api/classes fails', async () => {
    req.mockImplementation((_m: string, path: string) => {
      if (path === '/api/classes') return Promise.reject(new Error('boom'))
      if (path.endsWith('/analytics')) return Promise.resolve(stats(7))
      return Promise.resolve({ id: 1, class_id: 1, subject: 'math', title: '周测' })
    })
    renderOverview()
    expect(screen.getByText('加载中…')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('7 / 10')).toBeTruthy())
  })

  it('clears previous data and shows error when the next assignment fails', async () => {
    req.mockImplementation((_m: string, path: string) => {
      if (path === '/api/classes') return Promise.resolve([])
      if (path.includes('/2')) return Promise.reject(new Error('没有这个作业'))
      if (path.endsWith('/analytics')) return Promise.resolve(stats(7))
      return Promise.resolve({ id: 1, class_id: 1, subject: 'math', title: '周测' })
    })
    renderOverview()
    await waitFor(() => expect(screen.getByText('7 / 10')).toBeTruthy())
    fireEvent.click(screen.getByText('go2'))
    await waitFor(() => expect(screen.getByText('没有这个作业')).toBeTruthy())
    expect(screen.queryByText('7 / 10')).toBeNull()
  })
})

describe('Home states', () => {
  it('clears the error and stale list when switching class', async () => {
    req.mockImplementation((_m: string, path: string) => {
      if (path === '/api/classes') return Promise.resolve([{ id: 1, name: '一班', grade: 1 }, { id: 2, name: '二班', grade: 1 }])
      if (path.includes('/1/')) return Promise.reject(new Error('出错了'))
      return Promise.resolve([{ id: 9, class_id: 2, subject: 'math', title: '二班作业' }])
    })
    render(<MemoryRouter><Home /></MemoryRouter>)
    expect(screen.getByText('加载中…')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('出错了')).toBeTruthy())
    fireEvent.click(screen.getByText('二班'))
    await waitFor(() => expect(screen.getByRole('link', { name: /^数学 二班作业/ })).toBeTruthy())
    expect(screen.queryByText('出错了')).toBeNull()
  })
})
