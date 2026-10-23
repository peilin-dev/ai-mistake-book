import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/lib/api', () => ({
  request: vi.fn(),
  errorText: (e: unknown) => (e instanceof Error ? e.message : 'x'),
  ApiError: class extends Error {},
  setOnUnauthorized: () => {},
}))
vi.mock('../src/components/Header', () => ({ default: () => null }))

import { request } from '../src/lib/api'
import Downloads from '../src/pages/Downloads'

const req = request as unknown as ReturnType<typeof vi.fn>
afterEach(() => { cleanup(); req.mockReset(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('Downloads signature dialog', () => {
  it('double click on 保存并下载 sends one PATCH and one export', async () => {
    let releasePatch: (v: unknown) => void = () => {}
    req.mockImplementation((m: string, path: string) => {
      if (path === '/api/me' && m === 'GET') return Promise.resolve({ id: 1, display_name: null, last_subject: null })
      if (path === '/api/me' && m === 'PATCH') {
        return new Promise((r) => { releasePatch = () => r({ id: 1, display_name: '王老师', last_subject: null }) })
      }
      if (path.endsWith('/practice')) return Promise.reject(Object.assign(new Error('x'), { status: 404 }))
      if (path.endsWith('/exports')) return Promise.resolve({ url: '/api/files/a', filename: 'a.pdf' })
      return Promise.reject(new Error('unexpected'))
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(new Blob(['x'])) }))
    URL.createObjectURL = vi.fn(() => 'blob:1')
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    render(
      <MemoryRouter initialEntries={['/a/3/downloads']}>
        <Routes><Route path="/a/:assignmentId/downloads" element={<Downloads />} /></Routes>
      </MemoryRouter>,
    )
    await waitFor(() => expect(req).toHaveBeenCalledWith('GET', '/api/assignments/3/practice'))
    fireEvent.click(screen.getAllByText('下载 PDF')[0])
    const input = await screen.findByPlaceholderText('例如 王老师')
    fireEvent.change(input, { target: { value: '王老师' } })
    const save = screen.getByText('保存并下载')
    fireEvent.click(save)
    fireEvent.click(save)
    releasePatch(null)
    await waitFor(() => expect(req.mock.calls.filter((c) => c[2] !== undefined && c[1].endsWith('/exports'))).toHaveLength(1))
    await new Promise((r) => setTimeout(r, 20))
    expect(req.mock.calls.filter((c) => c[0] === 'PATCH')).toHaveLength(1)
    expect(req.mock.calls.filter((c) => c[1].endsWith('/exports'))).toHaveLength(1)
  })
})

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/a/3/downloads']}>
      <Routes><Route path="/a/:assignmentId/downloads" element={<Downloads />} /></Routes>
    </MemoryRouter>,
  )
}

function mockApi(displayName: string | null, practiceStatus: string | null) {
  req.mockImplementation((m: string, path: string) => {
    if (path === '/api/me' && m === 'GET') return Promise.resolve({ id: 1, display_name: displayName, last_subject: null })
    if (path === '/api/me' && m === 'PATCH') return Promise.resolve({ id: 1, display_name: '王老师', last_subject: null })
    if (path.endsWith('/practice')) {
      return practiceStatus ? Promise.resolve({ status: practiceStatus })
        : Promise.reject(Object.assign(new Error('x'), { status: 404 }))
    }
    if (path.endsWith('/exports')) return Promise.resolve({ url: '/api/files/exports/x.pdf?sig=1', filename: 'a.pdf' })
    return Promise.reject(new Error('unexpected'))
  })
}

function fakeTab() {
  return { document: { title: '', body: { textContent: '' } }, location: { href: '' }, close: vi.fn() }
}

describe('Downloads online view', () => {
  it('only the lecture and practice sheets can be viewed online; the name-bearing sheet is download-only', async () => {
    mockApi('王老师', 'done')
    renderPage()
    await waitFor(() => expect(screen.getAllByText('在线查看')).toHaveLength(2))
    const cards = Array.from(document.querySelectorAll('.dl-card'))
    const sheetCard = cards.find((c) => c.textContent?.includes('全班错题单'))!
    expect(sheetCard.textContent).not.toContain('在线查看')
    expect(sheetCard.textContent).toContain('含学生姓名')
  })

  it('opens the tab inside the click, then points it at the PDF', async () => {
    mockApi('王老师', 'done')
    const tab = fakeTab()
    const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    renderPage()
    await waitFor(() => expect(req).toHaveBeenCalledWith('GET', '/api/me'))
    fireEvent.click(screen.getAllByText('在线查看')[0])
    expect(open).toHaveBeenCalledTimes(1)  // synchronously, before any await
    await waitFor(() => expect(tab.location.href).toBe('/api/files/exports/x.pdf?sig=1'))
    expect(req).toHaveBeenCalledWith('POST', '/api/assignments/3/exports', { kind: 'lecture' })
  })

  it('practice view sends the answers checkbox', async () => {
    mockApi('王老师', 'done')
    const tab = fakeTab()
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    renderPage()
    const box = await screen.findByRole('checkbox') as HTMLInputElement
    await waitFor(() => expect(box.disabled).toBe(false))
    fireEvent.click(box)
    fireEvent.click(screen.getAllByText('在线查看')[1])
    await waitFor(() => expect(req).toHaveBeenCalledWith('POST', '/api/assignments/3/exports',
      { kind: 'practice', include_answers: false }))
  })

  it('a blocked popup shows a hint and exports nothing', async () => {
    mockApi('王老师', 'done')
    vi.spyOn(window, 'open').mockReturnValue(null)
    renderPage()
    await waitFor(() => expect(req).toHaveBeenCalledWith('GET', '/api/me'))
    fireEvent.click(screen.getAllByText('在线查看')[0])
    expect(await screen.findByText(/允许本网站弹出窗口/)).toBeTruthy()
    expect(req.mock.calls.filter((c) => c[1].endsWith('/exports'))).toHaveLength(0)
  })

  it('a failed export closes the waiting tab', async () => {
    mockApi('王老师', 'done')
    req.mockImplementation((m: string, path: string) => {
      if (path === '/api/me') return Promise.resolve({ id: 1, display_name: '王老师', last_subject: null })
      if (path.endsWith('/practice')) return Promise.resolve({ status: 'done' })
      return Promise.reject(new Error('生成失败'))
    })
    const tab = fakeTab()
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window)
    renderPage()
    await waitFor(() => expect(req).toHaveBeenCalledWith('GET', '/api/me'))
    fireEvent.click(screen.getAllByText('在线查看')[0])
    expect(await screen.findByText('生成失败')).toBeTruthy()
    expect(tab.close).toHaveBeenCalled()
  })

  it('without a signature the dialog click opens the tab', async () => {
    mockApi(null, 'done')
    const first = fakeTab()
    const second = fakeTab()
    const open = vi.spyOn(window, 'open')
      .mockReturnValueOnce(first as unknown as Window).mockReturnValueOnce(second as unknown as Window)
    renderPage()
    await waitFor(() => expect(req).toHaveBeenCalledWith('GET', '/api/me'))
    fireEvent.click(screen.getAllByText('在线查看')[0])
    const input = await screen.findByPlaceholderText('例如 王老师')
    expect(first.close).toHaveBeenCalled()  // the tab opened by the first click is not left blank
    fireEvent.change(input, { target: { value: '王老师' } })
    fireEvent.click(screen.getByText('保存并查看'))
    expect(open).toHaveBeenCalledTimes(2)
    await waitFor(() => expect(second.location.href).toBe('/api/files/exports/x.pdf?sig=1'))
  })
})
