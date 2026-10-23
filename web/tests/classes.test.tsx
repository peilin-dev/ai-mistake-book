import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
import ClassDetail from '../src/pages/ClassDetail'
import ClassNew from '../src/pages/ClassNew'
import Confirm from '../src/components/Confirm'

const req = request as unknown as ReturnType<typeof vi.fn>
afterEach(() => { cleanup(); req.mockReset() })

const classes = [{ id: 7, name: '五年级1班', grade: 5 }]
const students = [
  { id: 1, name: '张三', student_no: '01' },
  { id: 2, name: '李四', student_no: null },
]

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<p>首页</p>} />
        <Route path="/classes/new" element={<ClassNew />} />
        <Route path="/classes/:classId" element={<ClassDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

function mockDetail(extra?: (m: string, p: string, b?: unknown) => unknown) {
  req.mockImplementation((m: string, p: string, b?: unknown) => {
    const r = extra?.(m, p, b)
    if (r !== undefined) return r
    if (m === 'GET' && p === '/api/classes') return Promise.resolve(classes)
    if (m === 'GET' && p === '/api/classes/7/students') return Promise.resolve(students)
    return Promise.reject(new Error('unexpected ' + m + ' ' + p))
  })
}

describe('creating a class', () => {
  it('creating a class imports the pasted roster', async () => {
    mockDetail((m, p) => {
      if (m === 'POST' && p === '/api/classes') return Promise.resolve({ id: 7, name: '六年级2班', grade: 6 })
      if (m === 'POST' && p === '/api/classes/7/students:import') {
        return Promise.resolve({ created: 2, students })
      }
      return undefined
    })
    renderApp('/classes/new')
    fireEvent.change(screen.getByLabelText('年级'), { target: { value: '6' } })
    fireEvent.change(screen.getByLabelText('班级名称'), { target: { value: '六年级2班' } })
    fireEvent.change(screen.getByLabelText(/^学生名单/), { target: { value: '张三 01\n李四\n李四\n王五' } })
    expect(screen.getByText('识别到 3 人')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '建班并导入 3 人' }))
    // lands on the class page with the import summary: 3 recognized, 2 created, 1 skipped
    await screen.findByText('新增 2 人，跳过重复 1 人')
    expect(req).toHaveBeenCalledWith('POST', '/api/classes', { name: '六年级2班', grade: 6 })
    expect(req).toHaveBeenCalledWith('POST', '/api/classes/7/students:import', { text: '张三 01\n李四\n李四\n王五' })
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('五年级1班')
  })

  it('refuses an empty class name without calling the API', async () => {
    renderApp('/classes/new')
    fireEvent.change(screen.getByLabelText('班级名称'), { target: { value: '  ' } })
    fireEvent.click(screen.getByRole('button', { name: '建班' }))
    expect((await screen.findByRole('alert')).textContent).toContain('班级名称')
    expect(req).not.toHaveBeenCalled()
  })
})

describe('class page', () => {
  it('deleting a class asks for confirmation first', async () => {
    mockDetail((m, p) => (m === 'DELETE' && p === '/api/classes/7' ? Promise.resolve(undefined) : undefined))
    renderApp('/classes/7')
    fireEvent.click(await screen.findByRole('button', { name: '删除班级' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog.textContent).toContain('作业和成绩会一起删除，无法恢复')
    expect(req).not.toHaveBeenCalledWith('DELETE', '/api/classes/7')
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(req).not.toHaveBeenCalledWith('DELETE', '/api/classes/7')

    fireEvent.click(screen.getByRole('button', { name: '删除班级' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '确认删除' }))
    await screen.findByText('首页')
    expect(req).toHaveBeenCalledWith('DELETE', '/api/classes/7')
  })

  it('deleting a student asks for confirmation first', async () => {
    mockDetail((m, p) => (m === 'DELETE' && p === '/api/students/2' ? Promise.resolve(undefined) : undefined))
    renderApp('/classes/7')
    fireEvent.click(await screen.findByRole('button', { name: '删除 李四' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog.textContent).toContain('李四')
    expect(req).not.toHaveBeenCalledWith('DELETE', '/api/students/2')
    fireEvent.click(within(dialog).getByRole('button', { name: '确认删除' }))
    await waitFor(() => expect(req).toHaveBeenCalledWith('DELETE', '/api/students/2'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('shows the backend reason when a student cannot be deleted', async () => {
    mockDetail((m, p) =>
      m === 'DELETE' && p === '/api/students/1'
        ? Promise.reject(new Error('已有成绩的学生不能删除，可以改名'))
        : undefined)
    renderApp('/classes/7')
    fireEvent.click(await screen.findByRole('button', { name: '删除 张三' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '确认删除' }))
    expect((await screen.findByRole('alert')).textContent).toContain('已有成绩的学生不能删除')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('renames a student', async () => {
    mockDetail((m, p, b) =>
      m === 'PATCH' && p === '/api/students/2'
        ? Promise.resolve({ id: 2, ...(b as object) })
        : undefined)
    renderApp('/classes/7')
    fireEvent.click(await screen.findByRole('button', { name: '修改 李四' }))
    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '李思' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(req).toHaveBeenCalledWith('PATCH', '/api/students/2', { name: '李思', student_no: null }))
  })

  it('appends a roster and reports added and skipped', async () => {
    mockDetail((m, p) =>
      m === 'POST' && p === '/api/classes/7/students:import'
        ? Promise.resolve({ created: 1, students })
        : undefined)
    renderApp('/classes/7')
    fireEvent.change(await screen.findByLabelText('追加名单'), { target: { value: '张三 01\n赵六' } })
    fireEvent.click(screen.getByRole('button', { name: '追加 2 人' }))
    await screen.findByText('新增 1 人，跳过重复 1 人')
  })
})

describe('Confirm', () => {
  it('focuses the safe button, cancels on Escape', () => {
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(<Confirm title="删除？" message="不可恢复" confirmText="确认删除" danger onConfirm={onConfirm} onCancel={onCancel} />)
    const dialog = screen.getByRole('dialog')
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '取消' }))
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
