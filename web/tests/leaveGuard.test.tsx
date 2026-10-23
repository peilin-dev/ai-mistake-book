import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import {
  createMemoryRouter,
  Link,
  Outlet,
  RouterProvider,
} from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LeaveGuard from '../src/components/LeaveGuard'
import { useLeaveGuard } from '../src/lib/useLeaveGuard'
// Node's fetch Request rejects jsdom's AbortSignal realm. These tests have no
// loaders and only exercise navigation, so omit that foreign signal in Request.
beforeEach(() => {
  const NativeRequest = globalThis.Request
  vi.stubGlobal(
    'Request',
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(input, { ...init, signal: undefined })
      }
    },
  )
})
function Editing() {
  useLeaveGuard(true, '还有卷子没传完，确定离开吗？')
  return (
    <>
      <p>上传中</p>
      <Link to="/done">去作业页</Link>
    </>
  )
}
function mount() {
  const router = createMemoryRouter(
    [
      {
        element: (
          <>
            <LeaveGuard />
            <Outlet />
          </>
        ),
        children: [
          { path: '/edit', element: <Editing /> },
          { path: '/done', element: <p>作业页</p> },
        ],
      },
    ],
    { initialEntries: ['/done', '/edit'] },
  )
  render(<RouterProvider router={router} />)
  return router
}
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
describe('leave guard', () => {
  it('keeps work on screen when a route change is declined', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mount()
    await screen.findByText('上传中')
    fireEvent.click(screen.getByText('去作业页'))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(screen.getByText('上传中')).toBeTruthy()
  })
  it('allows a route change after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await screen.findByText('上传中')
    fireEvent.click(screen.getByText('去作业页'))
    expect(await screen.findByText('作业页')).toBeTruthy()
  })
  it('also guards browser history navigation and cancellation of logout', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const router = mount()
    await screen.findByText('上传中')
    await router.navigate(-1)
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(screen.getByText('上传中')).toBeTruthy()
    expect(
      window.dispatchEvent(new Event('teacher-logout', { cancelable: true })),
    ).toBe(false)
  })
})
