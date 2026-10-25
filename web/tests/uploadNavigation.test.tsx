import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/components/Header', () => ({ default: () => null }))
vi.mock('../src/components/PageThumbnail', () => ({ default: () => null }))
vi.mock('../src/lib/api', async () => ({ ...await vi.importActual('../src/lib/api'), request: vi.fn() }))
vi.mock('../src/lib/intake', async () => ({ ...await vi.importActual('../src/lib/intake'), expandFiles: vi.fn(), toJpeg: vi.fn(async () => new Blob()) }))
import { ApiError, request } from '../src/lib/api'
import { expandFiles } from '../src/lib/intake'
import LeaveGuard from '../src/components/LeaveGuard'
import Upload from '../src/pages/Upload'
import AssignmentWork from '../src/pages/AssignmentWork'

const req = vi.mocked(request), expand = vi.mocked(expandFiles)
beforeEach(() => {
  req.mockReset(); expand.mockReset()
  // React Router's navigation Request uses a different AbortSignal realm in jsdom.
  const NativeRequest = globalThis.Request
  vi.stubGlobal('Request', class extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) { super(input, { ...init, signal: undefined }) }
  })
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

async function mount(options: { remaining?: number; bad?: boolean; failSecond?: boolean; quotaSecond?: boolean } = {}) {
  let uploads = 0
  req.mockImplementation(async (method, path) => {
    if (path === '/api/me') return { quota_total: options.remaining ?? 10, quota_used: 0 }
    if (method === 'POST') {
      uploads++
      if (uploads === 2 && options.failSecond) throw new Error('网络异常')
      if (uploads === 2 && options.quotaSecond) throw new ApiError(429, '额度已用完')
      return { duplicate: uploads === 1 }
    }
    if (path.endsWith('/progress')) return { total: 2, queued: 0, processing: 0, done: 2, failed: 0, needs_review: 0 }
    if (path.endsWith('/pages')) return []
    return { title: '上传测试' }
  })
  expand.mockResolvedValue({ pages: [1, 2].map(id => ({ id: String(id), fileName: `${id}.jpg`, pageNo: null, takenAt: null, load: async () => new Blob() })), bad: options.bad ? [{ fileName: 'bad.pdf', reason: '文件损坏' }] : [] })
  const router = createMemoryRouter([{ element: <><LeaveGuard /><Outlet /></>, children: [
    { path: '/a/:assignmentId/upload', element: <Upload /> },
    { path: '/a/:assignmentId/work', element: <AssignmentWork /> },
  ] }], { initialEntries: ['/a/7/upload'] })
  const { container } = render(<RouterProvider router={router} />)
  await screen.findByText(/本月还能批改/)
  fireEvent.change(container.querySelector('input[type=file]')!, { target: { files: [new File(['x'], '1.jpg')] } })
  await screen.findByText('本批共 2 页')
  return router
}

describe('upload completion navigation', () => {
  it('opens progress after every page is accepted, including duplicates, without a leave prompt', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const router = await mount()
    fireEvent.click(screen.getByRole('button', { name: '开始上传' }))
    await screen.findByText(/上传已完成，可在下方查看批改进度/)
    expect(router.state.location.pathname).toBe('/a/7/work')
    expect(router.state.historyAction).toBe('REPLACE')
    expect(screen.getByText(/上传已完成，可在下方查看批改进度/).textContent).toContain('上传 1 页，跳过重复 1 页，失败 0 页')
    expect(confirm).not.toHaveBeenCalled()
  })
  it('keeps failures available for retry and navigates only after the retry succeeds', async () => {
    const router = await mount({ failSecond: true })
    fireEvent.click(screen.getByRole('button', { name: '开始上传' }))
    fireEvent.click(await screen.findByRole('button', { name: '重试' }))
    await screen.findByText(/上传已完成，可在下方查看批改进度/)
    expect(router.state.location.pathname).toBe('/a/7/work')
  })
  it('stays on upload when the user sends only the pages covered by remaining quota', async () => {
    const router = await mount({ remaining: 1 })
    fireEvent.click(screen.getByRole('button', { name: '只传前 1 页' }))
    await screen.findByText('上传 0 页，跳过重复 1 页，失败 0 页')
    expect(router.state.location.pathname).toBe('/a/7/upload')
    expect(screen.getByText('等待上传')).toBeTruthy()
  })
  it('stays on upload for server quota stops and files that could not be added', async () => {
    const router = await mount({ quotaSecond: true, bad: true })
    fireEvent.click(screen.getByRole('button', { name: '开始上传' }))
    await screen.findByText(/本月额度已用完，剩下 1 页没有上传/)
    expect(router.state.location.pathname).toBe('/a/7/upload')
    expect(screen.getByText('bad.pdf：文件损坏')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('额度不足，未上传')).toBeTruthy())
  })
})
