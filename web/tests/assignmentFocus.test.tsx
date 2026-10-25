import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import AssignmentFocus from '../src/components/AssignmentFocus'
import { request } from '../src/lib/api'
vi.mock('../src/lib/api', async () => ({ ...await vi.importActual('../src/lib/api'), request: vi.fn() }))
const assignment = { id: 7, class_id: 2, subject: 'math', title: '二次函数练习' }
const completed = { total: 2, queued: 0, processing: 0, done: 2, failed: 0, needs_review: 1 }
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers() })
it('uses actual page ownership and review counts for scoped shortcuts', async () => {
  vi.mocked(request).mockImplementation(async (_, path) => path.endsWith('/progress') ? completed : [{ status: 'done', student_id: null }, { status: 'done', student_id: 8 }])
  render(<MemoryRouter><AssignmentFocus assignment={assignment} /></MemoryRouter>)
  expect((await screen.findByRole('link', { name: '认领 1 页' })).getAttribute('href')).toBe('/a/7/claim')
  expect(screen.getByRole('link', { name: '复核 1 题' }).getAttribute('href')).toBe('/a/7/review')
  expect(screen.getByText('100%')).toBeTruthy()
  expect(screen.getByRole('link', { name: '认领与复核' }).getAttribute('aria-current')).toBe('step')
})
it('polls real progress and stops once processing completes', async () => {
  let calls = 0
  vi.mocked(request).mockImplementation(async (_, path) => path.endsWith('/progress') ? (++calls === 1 ? { ...completed, done: 1, processing: 1 } : { ...completed, needs_review: 0 }) : [])
  vi.useFakeTimers()
  render(<MemoryRouter><AssignmentFocus assignment={assignment} /></MemoryRouter>)
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  expect(screen.getByText('50%')).toBeTruthy()
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getByText('100%')).toBeTruthy()
  await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
  expect(calls).toBe(2)
})
it('offers retry on failure without inventing zero counts', async () => {
  vi.mocked(request).mockRejectedValueOnce(new Error('网络异常')).mockResolvedValue([])
  render(<MemoryRouter><AssignmentFocus assignment={assignment} /></MemoryRouter>)
  expect(await screen.findByRole('button', { name: '重试读取状态' })).toBeTruthy()
  expect(screen.queryByText('0%')).toBeNull()
  vi.mocked(request).mockImplementation(async (_, path) => path.endsWith('/progress') ? completed : [])
  fireEvent.click(screen.getByRole('button', { name: '重试读取状态' }))
  await waitFor(() => expect(screen.getByText('100%')).toBeTruthy())
})
