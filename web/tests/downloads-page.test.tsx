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
