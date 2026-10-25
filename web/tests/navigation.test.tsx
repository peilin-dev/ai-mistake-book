import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/lib/api', () => ({ request: vi.fn(), errorText: (e: Error) => e.message }))
import { request } from '../src/lib/api'
import Header from '../src/components/Header'
import Home from '../src/pages/Home'

const req = vi.mocked(request)
afterEach(() => { cleanup(); req.mockReset() })
function Location() { const loc = useLocation(); return <output aria-label="当前地址">{loc.pathname + loc.search}</output> }
function mockData() {
  req.mockImplementation((_method, path) => Promise.resolve(path === '/api/me'
    ? { id: 1, display_name: '林老师', quota_used: 3, quota_total: 30 }
    : path === '/api/classes' ? [{ id: 2, name: '五年级二班', grade: 5 }]
    : [{ id: 7, class_id: 2, title: '小数单元练习', subject: 'math' }]) as ReturnType<typeof request>)
}

describe('workspace navigation', () => {
  it('switches assignment layout without dropping filters and exposes scoped quick actions', async () => {
    mockData()
    const { container } = render(<MemoryRouter initialEntries={['/?class=2&subject=math']}><Home /><Location /></MemoryRouter>)
    const actions = await screen.findByRole('navigation', { name: '小数单元练习快捷操作' })
    expect(within(actions).getByRole('link', { name: '上传' }).getAttribute('href')).toBe('/a/7/upload')
    expect(within(actions).getByRole('link', { name: '成绩' }).getAttribute('href')).toBe('/a/7/grades')
    fireEvent.click(screen.getByRole('button', { name: '列表' }))
    expect(screen.getByLabelText('当前地址').textContent).toContain('subject=math')
    expect(screen.getByLabelText('当前地址').textContent).toContain('layout=list')
    expect(container.querySelector('.assignment-list.is-list-view')).toBeTruthy()
  })
  it('searches assignments without losing the selected class', async () => {
    mockData()
    render(<MemoryRouter initialEntries={['/?class=2']}><Header /><Location /></MemoryRouter>)
    fireEvent.change(screen.getByRole('searchbox', { name: '搜索作业' }), { target: { value: ' 小数 ' } })
    fireEvent.submit(screen.getByRole('search'))
    expect(screen.getByLabelText('当前地址').textContent).toBe('/?class=2&q=%E5%B0%8F%E6%95%B0')
    await screen.findByRole('button', { name: /林老师/ })
  })

  it('links every operation to the current assignment and marks its location', async () => {
    mockData()
    render(<MemoryRouter initialEntries={['/a/7/review']}><Routes><Route path="/a/:assignmentId/review" element={<Header />} /></Routes></MemoryRouter>)
    expect(screen.getByRole('link', { name: '复核' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: '下载打印' }).getAttribute('href')).toBe('/a/7/downloads')
    fireEvent.click(screen.getByRole('button', { name: '折叠侧边栏' }))
    expect(screen.getByRole('button', { name: '展开侧边栏' }).getAttribute('aria-expanded')).toBe('false')
    expect(screen.getByRole('link', { name: '上传卷子' }).getAttribute('href')).toBe('/a/7/upload')
    await screen.findByRole('button', { name: /林老师/ })
  })

  it('closes mobile navigation with Escape and restores focus and scrolling', async () => {
    mockData()
    render(<MemoryRouter><Header /></MemoryRouter>)
    const toggle = screen.getByRole('button', { name: '打开导航' })
    fireEvent.click(toggle)
    expect(document.body.style.overflow).toBe('hidden')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(toggle)
    expect(document.body.style.overflow).toBe('')
    await screen.findByRole('button', { name: /林老师/ })
  })

  it('opens the real class directory and its roster and assignment destinations', async () => {
    mockData()
    render(<MemoryRouter initialEntries={['/?view=classes']}><Home /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: '五年级二班' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /查看作业/ }).getAttribute('href')).toBe('/?class=2')
    expect(screen.getByRole('link', { name: '管理名单' }).getAttribute('href')).toBe('/classes/2')
    await waitFor(() => expect(screen.getByRole('link', { name: '我的班级' }).getAttribute('aria-current')).toBe('page'))
  })
})
