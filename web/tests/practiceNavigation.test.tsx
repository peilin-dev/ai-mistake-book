import { cleanup, fireEvent, render, screen, waitFor, act } from '@testing-library/react'
import { MemoryRouter, Link, Routes, Route } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
vi.mock('../src/components/WorkShell', () => ({ default: ({children}: {children: React.ReactNode}) => <div>{children}</div> }))
vi.mock('../src/lib/api', async () => ({ ...(await vi.importActual<typeof import('../src/lib/api')>('../src/lib/api')), request: vi.fn() }))
import { request } from '../src/lib/api'
import Practice from '../src/pages/Practice'
afterEach(() => { cleanup(); vi.resetAllMocks() })
const paper = (stem: string) => ({ id: 1, status: 'done', items: [{ id: 101, position: 1, stem, options: null, answer: 'A', replacing: false }] })
function mount() {
 return render(<MemoryRouter initialEntries={['/a/7/practice']}><Link to="/a/8/practice">切换作业</Link><Routes><Route path="/a/:assignmentId/practice" element={<Practice/>}/></Routes></MemoryRouter>)
}
it('removes old questions immediately and keeps generation disabled if the next paper fails to load', async () => {
 let rejectLoad!: (e: Error) => void
 vi.mocked(request).mockImplementation(async (_, path) => path.includes('/8/') ? new Promise((_, reject) => { rejectLoad = reject }) : paper('旧作业题目'))
 mount()
 await screen.findByText('旧作业题目')
 fireEvent.click(screen.getByText('切换作业'))
 expect(screen.queryByText('旧作业题目')).toBeNull()
 expect(screen.queryByRole('button', {name: '换一道'})).toBeNull()
 await act(async () => rejectLoad(new Error('加载失败')))
 await screen.findByRole('alert')
 expect((screen.getByRole('button', {name: '生成练习卷'}) as HTMLButtonElement).disabled).toBe(true)
})
it('ignores generation finishing for the old assignment after navigation', async () => {
 let finish!: (value: unknown) => void
 vi.mocked(request).mockImplementation(async (method, path) => {
  if (method === 'POST') return new Promise(resolve => { finish = resolve })
  return path.includes('/8/') ? paper('新作业题目') : { ...paper(''), items: [] }
 })
 mount()
 const generate = await screen.findByRole('button', {name: '生成练习卷'})
 await waitFor(() => expect((generate as HTMLButtonElement).disabled).toBe(false))
 fireEvent.click(generate)
 fireEvent.click(screen.getByText('切换作业'))
 await screen.findByText('新作业题目')
 await act(async () => finish(paper('旧请求返回的题目')))
 expect(screen.queryByText('旧请求返回的题目')).toBeNull()
 expect(screen.getByText('新作业题目')).toBeTruthy()
})
