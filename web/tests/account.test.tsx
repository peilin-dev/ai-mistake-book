import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/lib/api', () => ({
  request: vi.fn(),
  errorText: (e: unknown) => (e instanceof Error ? e.message : 'x'),
  ApiError: class extends Error {},
  setOnUnauthorized: () => {},
}))

import { request } from '../src/lib/api'
import { publishMe } from '../src/lib/me'
import Header from '../src/components/Header'

const req = request as unknown as ReturnType<typeof vi.fn>
afterEach(() => { cleanup(); req.mockReset() })

const me = (name: string | null) => ({
  id: 1, display_name: name, last_subject: null, login_name: null, quota_total: 100, quota_used: 37,
})

function mockMe(name: string | null) {
  req.mockImplementation((m: string, path: string, body?: { display_name: string }) => {
    if (path === '/api/me' && m === 'GET') return Promise.resolve(me(name))
    if (path === '/api/me' && m === 'PATCH') return Promise.resolve(me(body!.display_name))
    return Promise.reject(new Error('unexpected'))
  })
}

function renderHeader() {
  render(<MemoryRouter><Header /></MemoryRouter>)
}

describe('account dialog', () => {
  it('clicking the name opens the dialog with the current name', async () => {
    mockMe('林老师')
    renderHeader()
    fireEvent.click(await screen.findByRole('button', { name: /林老师/ }))
    const dlg = await screen.findByRole('dialog')
    expect(dlg).toBeTruthy()
    expect((screen.getByLabelText('署名') as HTMLInputElement).value).toBe('林老师')
    expect(screen.getByText(/小程序和网页同时生效/)).toBeTruthy()
  })

  it('saving trims, PATCHes and updates the header', async () => {
    mockMe('林老师')
    renderHeader()
    fireEvent.click(await screen.findByRole('button', { name: /林老师/ }))
    fireEvent.change(await screen.findByLabelText('署名'), { target: { value: '  王老师  ' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(req).toHaveBeenCalledWith('PATCH', '/api/me', { display_name: '王老师' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByRole('button', { name: /王老师/ })).toBeTruthy()
  })

  it('empty or over-32 names show an error and are not sent', async () => {
    mockMe('林老师')
    renderHeader()
    fireEvent.click(await screen.findByRole('button', { name: /林老师/ }))
    const input = await screen.findByLabelText('署名')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(screen.getByRole('alert').textContent).toContain('请填写署名')
    fireEvent.change(input, { target: { value: '长'.repeat(33) } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(screen.getByRole('alert').textContent).toContain('32')
    expect(req.mock.calls.filter((c) => c[0] === 'PATCH')).toHaveLength(0)
  })

  it('no name shows 设置署名', async () => {
    mockMe(null)
    renderHeader()
    expect(await screen.findByRole('button', { name: /设置署名/ })).toBeTruthy()
  })

  it('dialog shows quota used / total', async () => {
    mockMe('林老师')
    renderHeader()
    fireEvent.click(await screen.findByRole('button', { name: /林老师/ }))
    expect((await screen.findByRole('dialog')).textContent).toContain('本月已批改 37 / 100 页')
  })

  it('a name published elsewhere (Downloads) updates the header', async () => {
    mockMe(null)
    renderHeader()
    await screen.findByRole('button', { name: /设置署名/ })
    act(() => publishMe(me('王老师')))
    expect(screen.getByRole('button', { name: /王老师/ })).toBeTruthy()
  })

  it('Esc closes the dialog and restores focus to the name button', async () => {
    mockMe('林老师')
    renderHeader()
    const btn = await screen.findByRole('button', { name: /林老师/ })
    btn.focus()
    fireEvent.click(btn)
    fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(btn)
  })
})
