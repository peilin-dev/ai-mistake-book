import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import BatchClaims from '../src/components/BatchClaims'
import { request } from '../src/lib/api'
vi.mock('../src/lib/api', async () => ({ ...await vi.importActual('../src/lib/api'), request: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
const queue = { pages: [1, 2].map(id => ({ page_id: id, seq: id, recognized_name: null, question_nos: [String(id)], image_url: null, suggested_student_id: null })), students: [{ id: 3, name: '张三', student_no: '001' }, { id: 4, name: '李四', student_no: '002' }] }
it('assigns selected pages together in one request and refreshes results', async () => {
  let saved = false
  vi.mocked(request).mockImplementation(async method => { if (method === 'POST') { saved = true; return { assigned: 2 } } return saved ? { ...queue, pages: [] } : queue })
  render(<MemoryRouter><BatchClaims assignmentId="7" /></MemoryRouter>)
  await screen.findByLabelText('选择第 1 页')
  expect((screen.getByRole('button', { name: '确认 0 页归属' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByLabelText('全选待归属页'))
  fireEvent.change(screen.getByLabelText('统一归属到学生'), { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: '确认 2 页归属' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith('POST', '/api/assignments/7/claims', { assignments: [{ page_id: 1, student_id: 3 }, { page_id: 2, student_id: 3 }] }))
  expect(await screen.findByText('无需手动归属')).toBeTruthy()
  expect(vi.mocked(request).mock.calls.filter(([method]) => method === 'POST')).toHaveLength(1)
})
it('supports different students in the same batch and retains choices on conflict', async () => {
  vi.mocked(request).mockImplementation(async method => { if (method === 'POST') throw Error('重复题号，请核对'); return queue })
  render(<MemoryRouter><BatchClaims assignmentId="7" /></MemoryRouter>)
  fireEvent.change(await screen.findByLabelText('第 1 页归属学生'), { target: { value: '3' } })
  fireEvent.change(screen.getByLabelText('第 2 页归属学生'), { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: '确认 2 页归属' }))
  await screen.findByRole('alert')
  expect(request).toHaveBeenCalledWith('POST', '/api/assignments/7/claims', { assignments: [{ page_id: 1, student_id: 3 }, { page_id: 2, student_id: 4 }] })
  expect((screen.getByLabelText('第 1 页归属学生') as HTMLSelectElement).value).toBe('3')
  expect((screen.getByLabelText('选择第 2 页') as HTMLInputElement).checked).toBe(true)
})
