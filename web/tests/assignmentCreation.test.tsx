import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import AssignmentNew from '../src/pages/AssignmentNew'
import AnswerKey from '../src/pages/AnswerKey'
import Upload from '../src/pages/Upload'
import { request } from '../src/lib/api'
import { expandFiles } from '../src/lib/intake'
vi.mock('../src/components/Header', () => ({ default: () => null }))
vi.mock('../src/components/PageThumbnail', () => ({ default: () => null }))
vi.mock('../src/lib/api', async () => ({ ...await vi.importActual('../src/lib/api'), request: vi.fn() }))
vi.mock('../src/lib/intake', async () => ({ ...await vi.importActual('../src/lib/intake'), expandFiles: vi.fn(), toJpeg: vi.fn(async () => new Blob()) }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it.each(['answer-key', 'upload'])('carries selected %s material into the next page without publishing unconfirmed answers', async kind => {
  vi.mocked(request).mockImplementation(async (method, path) => {
    if (path === '/api/classes') return [{ id: 2, name: '九年级', grade: 9 }, { id: 3, name: '六年级', grade: 6 }]
    if (path === '/api/me') return { last_subject: 'physics', quota_total: 100, quota_used: 0 }
    if (path === '/api/assignments') return { id: 7 }
    if (path.endsWith('/answer-key')) return { answer_key_status: 'none', items: method === 'POST' ? [{ question_no: '1', answer: '3N', max_score: 2, is_subjective: false }] : [] }
    return { subject: 'physics', grading_rules: null }
  })
  vi.mocked(expandFiles).mockResolvedValue({ pages: [{ id: 'a', fileName: '试卷.png', pageNo: null, takenAt: null, load: async () => new Blob() }], bad: [] })
  const { container } = render(<MemoryRouter initialEntries={['/classes/2/assignments/new']}><Routes>
    <Route path="/classes/:classId/assignments/new" element={<AssignmentNew />} />
    <Route path="/a/:assignmentId/answer-key" element={<AnswerKey />} />
    <Route path="/a/:assignmentId/upload" element={<Upload />} />
  </Routes></MemoryRouter>)
  await screen.findByDisplayValue('物理')
  fireEvent.change(screen.getByLabelText('作业名称'), { target: { value: '力学练习' } })
  if (kind === 'upload') fireEvent.click(screen.getByLabelText('学生已作答的卷子'))
  const file = new File(['image'], '试卷.png', { type: 'image/png' })
  fireEvent.change(container.querySelector('input[type=file]')!, { target: { files: [file] } })
  fireEvent.click(screen.getByRole('button', { name: kind === 'answer-key' ? '创建并核对答案' : '创建并预览卷子' }))
  await waitFor(() => expect(expandFiles).toHaveBeenCalledWith([file]))
  if (kind === 'answer-key') await screen.findByDisplayValue('3N')
  else await screen.findByText('本批共 1 页')
  expect(vi.mocked(request).mock.calls.some(([method]) => method === 'PUT')).toBe(false)
  expect(vi.mocked(request).mock.calls.filter(([method, path]) => method === 'POST' && path.endsWith('/pages'))).toHaveLength(0)
})
