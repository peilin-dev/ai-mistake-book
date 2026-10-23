import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/components/Header', () => ({ default: () => null }))
vi.mock('../src/components/StudentAssignment', () => ({ default: () => null }))
vi.mock('../src/components/PageThumbnail', () => ({ default: () => null }))
vi.mock('../src/lib/api', async () => {
  const actual =
    await vi.importActual<typeof import('../src/lib/api')>('../src/lib/api')
  return { ...actual, request: vi.fn() }
})
vi.mock('../src/lib/intake', async () => {
  const actual =
    await vi.importActual<typeof import('../src/lib/intake')>(
      '../src/lib/intake',
    )
  return {
    ...actual,
    expandFiles: vi.fn(),
    prepareOne: vi.fn(async () => new Blob()),
    toJpeg: vi.fn(async () => new Blob()),
  }
})
import { ApiError, request } from '../src/lib/api'
import { expandFiles } from '../src/lib/intake'
import AssignmentWork from '../src/pages/AssignmentWork'
import AssignmentNew from '../src/pages/AssignmentNew'
import Claim from '../src/pages/Claim'
import AnswerKey from '../src/pages/AnswerKey'
import Upload from '../src/pages/Upload'
import Review from '../src/pages/Review'
import Practice from '../src/pages/Practice'
const req = vi.mocked(request),
  expand = vi.mocked(expandFiles)
const answer = {
  question_no: '1',
  answer: 'A',
  max_score: 2,
  is_subjective: false,
}
function mount(
  page: React.ReactNode,
  path = '/a/:assignmentId/work',
  url = '/a/7/work',
) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path={path} element={page} />
        <Route path="/a/:assignmentId/work" element={<p>创建成功</p>} />
      </Routes>
    </MemoryRouter>,
  )
}
beforeEach(() => {
  req.mockReset()
  expand.mockReset()
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})
describe('teacher work pages', () => {
  it('creates an assignment with the last subject and correct class', async () => {
    req.mockImplementation(async (method, path, body) => {
      if (path === '/api/classes') return [{ id: 2, name: '五年级', grade: 5 }]
      if (path === '/api/me') return { last_subject: 'english' }
      if (method === 'POST' && path === '/api/assignments')
        return { id: 7, ...(body as object) }
      throw Error(path)
    })
    mount(
      <AssignmentNew />,
      '/classes/:classId/assignments/new',
      '/classes/2/assignments/new',
    )
    await waitFor(() =>
      expect((screen.getByLabelText('学科') as HTMLSelectElement).value).toBe(
        'english',
      ),
    )
    fireEvent.change(screen.getByLabelText('作业名称'), {
      target: { value: '  单元练习  ' },
    })
    fireEvent.click(screen.getByText('创建作业'))
    expect(await screen.findByText('创建成功')).toBeTruthy()
    expect(req).toHaveBeenCalledWith('POST', '/api/assignments', {
      class_id: 2,
      title: '单元练习',
      subject: 'english',
    })
  })
  it('asks before deleting a page and does not refund quota in its confirmation', async () => {
    req.mockImplementation(async (method, path) => {
      if (method === 'DELETE') return undefined
      if (path.endsWith('/pages'))
        return [
          {
            page_id: 9,
            seq: 1,
            status: 'failed',
            fail_reason: 'unreadable',
            student_id: null,
            source: 'web',
          },
        ]
      if (path.endsWith('/progress'))
        return {
          total: 1,
          queued: 0,
          processing: 0,
          done: 0,
          failed: 1,
          needs_review: 0,
        }
      return { title: '练习' }
    })
    mount(<AssignmentWork />)
    fireEvent.click(await screen.findByRole('button', { name: '删除' }))
    expect(req.mock.calls.some((c) => c[0] === 'DELETE')).toBe(false)
    expect(screen.getByRole('dialog').textContent).toContain('不退还')
    fireEvent.click(screen.getByRole('button', { name: '删除这一页' }))
    await waitFor(() =>
      expect(req).toHaveBeenCalledWith('DELETE', '/api/pages/9'),
    )
  })
  it('polls pending pages then stops once grading has finished', async () => {
    let progressCalls = 0
    req.mockImplementation(async (_, path) => {
      if (path.endsWith('/progress')) {
        progressCalls++
        return {
          total: 1,
          queued: progressCalls === 1 ? 1 : 0,
          processing: 0,
          done: progressCalls === 1 ? 0 : 1,
          failed: 0,
          needs_review: 0,
        }
      }
      if (path.endsWith('/pages')) return []
      return { title: '练习' }
    })
    vi.useFakeTimers()
    mount(<AssignmentWork />)
    await vi.advanceTimersByTimeAsync(0)
    expect(progressCalls).toBe(1)
    await vi.advanceTimersByTimeAsync(3000)
    expect(progressCalls).toBe(2)
    await vi.advanceTimersByTimeAsync(9000)
    expect(progressCalls).toBe(2)
  })
  it('confirms a preselected candidate with Enter and loads the next page', async () => {
    req.mockImplementation(async (method, path) => {
      if (method === 'PATCH') return {}
      if (path.endsWith('/review'))
        return { pages_unassigned: [{ page_id: 1 }, { page_id: 2 }] }
      return {
        page_id: path.includes('/1/') ? 1 : 2,
        image_url: null,
        question_nos: ['1'],
        candidates: [
          {
            student_id: 3,
            name: '张同学',
            missing_all: true,
            page_count: 0,
            thumb_url: null,
          },
        ],
      }
    })
    mount(<Claim />, '/a/:assignmentId/claim', '/a/7/claim')
    await screen.findByText('张同学')
    fireEvent.keyDown(window, { key: 'Enter' })
    await waitFor(() =>
      expect(req).toHaveBeenCalledWith('PATCH', '/api/pages/1', {
        student_id: 3,
      }),
    )
    await waitFor(() =>
      expect(req).toHaveBeenCalledWith('GET', '/api/pages/2/claim-candidates'),
    )
  })
  it('keeps a conflicting page in the claim queue and shows the server explanation', async () => {
    req.mockImplementation(async (method, path) => {
      if (method === 'PATCH') throw new ApiError(409, '页面尚未批改完成')
      if (path.endsWith('/review'))
        return { pages_unassigned: [{ page_id: 1 }] }
      return {
        page_id: 1,
        image_url: null,
        question_nos: [],
        candidates: [
          {
            student_id: 3,
            name: '张同学',
            missing_all: true,
            page_count: 0,
            thumb_url: null,
          },
        ],
      }
    })
    mount(<Claim />, '/a/:assignmentId/claim', '/a/7/claim')
    await screen.findByText('张同学')
    fireEvent.click(screen.getByText('确认归属'))
    expect(await screen.findByRole('alert')).toHaveProperty(
      'textContent',
      expect.stringContaining('页面尚未批改完成'),
    )
  })
  it('retries a failed answer page then sends the merged edited answers only once', async () => {
    let extracts = 0
    req.mockImplementation(async (method) => {
      if (method === 'POST') {
        extracts++
        if (extracts === 1) throw new TypeError('network')
        return { items: [answer] }
      }
      if (method === 'PUT') return { regrade_suggested: false }
      return { items: [], answer_key_status: 'none' }
    })
    expand.mockResolvedValue({
      pages: [
        {
          id: '1',
          fileName: 'answers.pdf',
          pageNo: 1,
          takenAt: null,
          load: async () => new Blob(),
        },
      ],
      bad: [],
    })
    const { container } = mount(
      <AnswerKey />,
      '/a/:assignmentId/answer-key',
      '/a/7/answer-key',
    )
    await waitFor(() =>
      expect(
        (container.querySelector('input[type=file]') as HTMLInputElement)
          .disabled,
      ).toBe(false),
    )
    fireEvent.change(container.querySelector('input[type=file]')!, {
      target: { files: [new File(['pdf'], 'answers.pdf')] },
    })
    fireEvent.click(await screen.findByText('重试这一页'))
    await screen.findByLabelText('第 1 行答案')
    fireEvent.change(screen.getByLabelText('第 1 行答案'), {
      target: { value: 'B' },
    })
    fireEvent.click(screen.getByText('确认保存'))
    fireEvent.click(screen.getByText('确认保存'))
    await waitFor(() =>
      expect(req.mock.calls.filter((c) => c[0] === 'PUT')).toHaveLength(1),
    )
    expect(req).toHaveBeenCalledWith('PUT', '/api/assignments/7/answer-key', {
      items: [{ ...answer, answer: 'B' }],
    })
  })
  it('blocks batches over 200 pages', async () => {
    req.mockResolvedValue({ quota_total: 500, quota_used: 0 })
    expand.mockResolvedValue({
      pages: Array.from({ length: 201 }, (_, i) => ({
        id: String(i),
        fileName: `${i}.jpg`,
        pageNo: null,
        takenAt: null,
        load: async () => new Blob(),
      })),
      bad: [],
    })
    const { container } = mount(
      <Upload />,
      '/a/:assignmentId/upload',
      '/a/7/upload',
    )
    fireEvent.change(container.querySelector('input[type=file]')!, {
      target: { files: [new File(['x'], 'x.jpg')] },
    })
    await screen.findByText(/一次最多上传 200 页，请分批上传/)
    expect(
      (screen.getByRole('button', { name: '开始上传' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)
  })
  it('offers to upload just the remaining quota', async () => {
    req.mockResolvedValue({ quota_total: 2, quota_used: 1 })
    expand.mockResolvedValue({
      pages: [1, 2].map((i) => ({
        id: String(i),
        fileName: `${i}.jpg`,
        pageNo: null,
        takenAt: null,
        load: async () => new Blob(),
      })),
      bad: [],
    })
    const { container } = mount(
      <Upload />,
      '/a/:assignmentId/upload',
      '/a/7/upload',
    )
    fireEvent.change(container.querySelector('input[type=file]')!, {
      target: { files: [new File(['x'], 'x.jpg')] },
    })
    expect(
      await screen.findByRole('button', { name: '只传前 1 页' }),
    ).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: '开始上传' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)
  })
  it('confirms an original grading result and removes the reviewed question', async () => {
    req.mockImplementation(async (method) =>
      method === 'PATCH'
        ? {}
        : {
            pages_unassigned: [],
            questions: [
              {
                id: 1,
                page_id: 2,
                question_no: '3',
                student_name: '张同学',
                score: 1,
                max_score: 2,
                is_correct: false,
                student_answer: 'A',
                correct_answer: 'B',
              },
            ],
          },
    )
    mount(<Review />, '/a/:assignmentId/review', '/a/7/review')
    fireEvent.click(await screen.findByText('确认原判'))
    await waitFor(() =>
      expect(req).toHaveBeenCalledWith('PATCH', '/api/question-results/1', {
        score: 1,
        is_correct: false,
      }),
    )
    expect(await screen.findByText('当前没有需要复核的题目了')).toBeTruthy()
  })
  it('requires confirmation before replacing an existing practice sheet', async () => {
    req.mockResolvedValue({
      id: 1,
      status: 'done',
      items: [
        {
          id: 1,
          position: 1,
          stem: '练习题',
          source_no: '1',
          answer: '2',
          options: null,
          replacing: false,
        },
      ],
      sources_done: 1,
      sources_total: 1,
    })
    mount(<Practice />, '/a/:assignmentId/practice', '/a/7/practice')
    fireEvent.click(await screen.findByText('重新生成练习卷'))
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(req.mock.calls.some((c) => c[0] === 'POST')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: '重新生成' }))
    await waitFor(() =>
      expect(req).toHaveBeenCalledWith('POST', '/api/assignments/7/practice'),
    )
  })
})
