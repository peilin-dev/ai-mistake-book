import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import AnswerKey from '../src/pages/AnswerKey'
import { request } from '../src/lib/api'
vi.mock('../src/components/Header', () => ({ default: () => null }))
vi.mock('../src/lib/api', async () => ({ ...await vi.importActual('../src/lib/api'), request: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
function setup(fail = false) {
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (path === '/api/classes') return [{ id: 2, name: '九年级一班', grade: 9 }]
    if (!path.endsWith('/answer-key')) return { id: 7, class_id: 2, title: '二次函数练习', subject: 'math', grading_rules: null }
    if (method === 'DELETE') { if (fail) throw Error('还有试卷正在批改'); return { regrade_suggested: true } }
    return { answer_key_status: 'confirmed', items: [{ question_no: '1', answer: '3', max_score: 2, is_subjective: false }] }
  })
  render(<MemoryRouter initialEntries={['/a/7/answer-key']}><Routes><Route path="/a/:assignmentId/answer-key" element={<AnswerKey />} /></Routes></MemoryRouter>)
}
it('shows the assignment and only deletes after confirmation, then resets the editor', async () => {
  setup()
  expect(await screen.findByRole('heading', { name: '二次函数练习' })).toBeTruthy()
  expect(screen.getByText(/九年级一班 · 数学 · 作业 #7/)).toBeTruthy()
  fireEvent.click(await screen.findByRole('button', { name: '删除整份答案卷' }))
  expect(vi.mocked(request).mock.calls.some(([method]) => method === 'DELETE')).toBe(false)
  expect(screen.getByRole('dialog').textContent).toContain('已有成绩不会自动重算')
  fireEvent.click(screen.getByRole('button', { name: '删除答案卷' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith('DELETE', '/api/assignments/7/answer-key'))
  expect(await screen.findByText(/答案卷已删除。后续批改使用 AI 建议答案/)).toBeTruthy()
  expect(screen.queryByDisplayValue('3')).toBeNull()
  expect(screen.queryByRole('button', { name: '删除整份答案卷' })).toBeNull()
})
it('keeps saved answers when deletion is rejected', async () => {
  setup(true)
  fireEvent.click(await screen.findByRole('button', { name: '删除整份答案卷' }))
  fireEvent.click(screen.getByRole('button', { name: '删除答案卷' }))
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.getByDisplayValue('3')).toBeTruthy()
})
it('does not carry old answer rows into another assignment while it is loading', async () => {
  vi.mocked(request).mockImplementation(async (_method, path) => {
    if (path.endsWith('/8/answer-key')) return new Promise(() => {})
    if (path.endsWith('/7/answer-key')) return { answer_key_status: 'confirmed', items: [{ question_no: '1', answer: '旧作业答案', max_score: 2, is_subjective: false }] }
    if (path === '/api/classes') return []
    return { title: path.endsWith('/8') ? '新作业' : '旧作业', subject: 'math', class_id: 2 }
  })
  render(<MemoryRouter initialEntries={['/a/7/answer-key']}><Routes><Route path="/a/:assignmentId/answer-key" element={<><Link to="/a/8/answer-key">切到另一份作业</Link><AnswerKey /></>} /></Routes></MemoryRouter>)
  await screen.findByDisplayValue('旧作业答案')
  fireEvent.click(screen.getByRole('link', { name: '切到另一份作业' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith('GET', '/api/assignments/8/answer-key'))
  expect(screen.queryByDisplayValue('旧作业答案')).toBeNull()
  expect((screen.getByRole('button', { name: '确认保存' }) as HTMLButtonElement).disabled).toBe(true)
})
