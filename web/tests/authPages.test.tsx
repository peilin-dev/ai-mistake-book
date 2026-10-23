import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/lib/api', async () => {
  const actual =
    await vi.importActual<typeof import('../src/lib/api')>('../src/lib/api')
  return { ...actual, request: vi.fn() }
})
import { ApiError, request } from '../src/lib/api'
import Login from '../src/pages/Login'
import Register from '../src/pages/Register'
import Credentials from '../src/components/Credentials'
const req = vi.mocked(request)
beforeEach(() => {
  req.mockReset()
  localStorage.clear()
})
afterEach(() => cleanup())
describe('account pages', () => {
  it('password login stores the token and returns to the original destination', async () => {
    req.mockResolvedValue({ token: 'test-token' })
    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/login', state: { from: '/a/7/work' } }]}
      >
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/a/7/work" element={<p>目标作业</p>} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.change(screen.getByLabelText('登录名'), {
      target: { value: 'teacher' },
    })
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'password8' },
    })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))
    expect(await screen.findByText('目标作业')).toBeTruthy()
    expect(localStorage.getItem('hbj_token')).toBe('test-token')
  })
  it('shows login errors without creating a QR ticket until that tab is chosen', async () => {
    req.mockRejectedValue(new ApiError(401, '登录名或密码不对'))
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )
    expect(req).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('登录名'), {
      target: { value: 'teacher' },
    })
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'password8' },
    })
    fireEvent.click(screen.getByRole('button', { name: '登录' }))
    expect(await screen.findByRole('alert')).toHaveProperty(
      'textContent',
      '登录名或密码不对',
    )
    expect(localStorage.getItem('hbj_token')).toBeNull()
  })
  it('keeps the WeChat QR flow available', async () => {
    req.mockResolvedValue({
      ticket: 'ticket',
      poll_key: 'key',
      pair_code: '1234',
      qr_png: 'abc',
      expires_in: 300,
    })
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: '微信扫码登录' }))
    await screen.findByAltText('小程序码')
    expect(req).toHaveBeenCalledWith('POST', '/api/web-login/tickets')
  })
  it('registration validates credentials locally and refreshes a used captcha after failure', async () => {
    let captchas = 0
    req.mockImplementation(async (_, path) => {
      if (path.endsWith('/captcha'))
        return { captcha_id: String(++captchas), image: 'abc' }
      throw new ApiError(400, '验证码不对或已过期')
    })
    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>,
    )
    await screen.findByAltText('图形验证码，点击更换')
    expect(req.mock.calls.some((c) => c[1] === '/api/me')).toBe(false)
    fireEvent.change(screen.getByLabelText('登录名'), {
      target: { value: 'a' },
    })
    fireEvent.change(screen.getByLabelText('密码'), {
      target: { value: 'password8' },
    })
    fireEvent.change(screen.getByLabelText('确认密码'), {
      target: { value: 'password8' },
    })
    fireEvent.change(screen.getByLabelText('图形验证码'), {
      target: { value: 'TEST' },
    })
    fireEvent.submit(
      screen.getByRole('button', { name: '注册' }).closest('form')!,
    )
    expect(await screen.findByRole('alert')).toHaveProperty(
      'textContent',
      expect.stringContaining('4–32'),
    )
    fireEvent.change(screen.getByLabelText('登录名'), {
      target: { value: 'teacher' },
    })
    fireEvent.submit(
      screen.getByRole('button', { name: '注册' }).closest('form')!,
    )
    await waitFor(() => expect(captchas).toBe(2))
    expect(
      (screen.getByLabelText('图形验证码') as HTMLInputElement).value,
    ).toBe('')
  })
  it('sets first-time credentials without asking for a current password', async () => {
    req.mockResolvedValue({ id: 1, display_name: null, login_name: 'teacher' })
    render(<Credentials me={{ id: 1, display_name: null, login_name: null }} />)
    expect(screen.queryByLabelText('当前密码')).toBeNull()
    fireEvent.change(screen.getByLabelText('登录名'), {
      target: { value: 'teacher' },
    })
    fireEvent.change(screen.getByLabelText('新密码'), {
      target: { value: 'password8' },
    })
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'password8' },
    })
    fireEvent.click(screen.getByText('保存登录设置'))
    await waitFor(() =>
      expect(req).toHaveBeenCalledWith('PUT', '/api/me/credentials', {
        login_name: 'teacher',
        password: 'password8',
        current_password: null,
      }),
    )
  })
  it('requires the current password when changing existing credentials', () => {
    render(
      <Credentials me={{ id: 1, display_name: null, login_name: 'teacher' }} />,
    )
    fireEvent.change(screen.getByLabelText('新密码'), {
      target: { value: 'password8' },
    })
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'password8' },
    })
    fireEvent.click(screen.getByText('保存登录设置'))
    expect(screen.getByRole('alert').textContent).toBe('请填写当前密码')
    expect(req).not.toHaveBeenCalled()
  })
})
