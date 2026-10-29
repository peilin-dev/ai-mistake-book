import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import Landing from '../src/pages/Landing'

afterEach(cleanup)
describe('product landing page', () => {
  it('switches demo content and keeps the sample label visible', () => {
    render(<MemoryRouter><Landing /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: /学情分析/ }))
    expect(screen.getByRole('heading', { name: '这节课，重点讲什么？' })).toBeTruthy()
    expect(screen.getByText('各知识点正确率 · 合成数据')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /巩固练习/ }))
    expect(screen.getByText('2(x − 3) = x + 4')).toBeTruthy()
    expect(screen.getByText('交互演示 · 示例数据')).toBeTruthy()
  })
  it('discloses unpublished plans instead of starting checkout', () => {
    render(<MemoryRouter><Landing /></MemoryRouter>)
    fireEvent.click(screen.getAllByRole('button', { name: /了解方案/ })[0])
    expect(screen.getByRole('status').textContent).toContain('尚未开放购买')
    expect(screen.getByRole('link', { name: '创建账号' }).getAttribute('href')).toBe('/register')
  })
  it('closes mobile navigation after selecting a section', () => {
    render(<MemoryRouter><Landing /></MemoryRouter>)
    const toggle = screen.getByRole('button', { name: '展开或关闭导航' })
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    const nav = screen.getByRole('navigation', { name: '移动导航' })
    fireEvent.click(nav.querySelector('a')!)
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
  })
})
