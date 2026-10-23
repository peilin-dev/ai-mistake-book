import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import themeCss from '../src/theme.css?raw'

vi.mock('../src/lib/api', () => ({
  request: vi.fn(),
  errorText: (e: unknown) => (e instanceof Error ? e.message : 'x'),
  ApiError: class extends Error {},
  setOnUnauthorized: () => {},
}))

import { request } from '../src/lib/api'
import Header from '../src/components/Header'
import Overview from '../src/pages/Overview'

const req = request as unknown as ReturnType<typeof vi.fn>
afterEach(() => { cleanup(); req.mockReset() })

const question = (no: string, wrong: number) => ({
  question_no: no, knowledge_point: null, wrong_count: wrong, student_count: 10, answered_count: 10,
  accuracy: (10 - wrong) / 10, top_wrong_answer: null, is_subjective: false,
})

function renderOverview(pending: number, questions = [question('1', 5), question('2', 4), question('3', 1)]) {
  req.mockImplementation((_m: string, path: string) => {
    if (path === '/api/me') return Promise.resolve({ id: 1, display_name: '林老师' })
    if (path === '/api/classes') return Promise.resolve([])
    if (path.endsWith('/analytics')) {
      return Promise.resolve({
        counted_students: 10, roster_size: 10, average_score: 5, average_ratio: 0.5, pass_rate: 0.5,
        pending_review: pending, pages_not_counted: 2,
        questions,
      })
    }
    return Promise.resolve({ id: 1, class_id: 1, subject: 'math', title: '周测' })
  })
  return render(
    <MemoryRouter initialEntries={['/a/1']}>
      <Routes><Route path="/a/:assignmentId" element={<Overview />} /></Routes>
    </MemoryRouter>,
  )
}

/** Declarations of the first rule whose selector list contains exactly `selector`. */
function ruleBody(css: string, selector: string): string {
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (m[1].split(',').map((s) => s.trim()).includes(selector)) return m[2]
  }
  return ''
}

describe('红笔君 identity', () => {
  it('header shows the seal brand', async () => {
    req.mockResolvedValue({ id: 1, display_name: '林老师' })
    const { container } = render(<MemoryRouter><Header /></MemoryRouter>)
    const link = screen.getByRole('link', { name: /红笔君/ })
    const seal = link.querySelector('img')
    expect(seal?.getAttribute('src')).toBe('/brand/seal-64.png')
    expect(seal?.getAttribute('width')).toBe('32')
    expect(link.querySelector('.serif')?.textContent).toBe('红笔君')
    // the old pen icon is no longer the logo
    expect(link.querySelector('svg')).toBeNull()
    await waitFor(() => expect(container.textContent).toContain('林老师'))
  })

  it('hot questions (>= 40%) are wrapped in RedCircle and not filled red', async () => {
    const { container } = renderOverview(0)
    await waitFor(() => expect(screen.getByText('第 1 题')).toBeTruthy())
    const cells = [...container.querySelectorAll('.q-cell')]
    const circled = (i: number) => cells[i].querySelector('.red-circle')
    // 50% and 40% are circled around the percentage; 10% is not
    expect(circled(0)?.textContent).toBe('50%')
    expect(circled(1)?.textContent).toBe('40%')
    expect(circled(2)).toBeNull()
    const mark = circled(0)!.querySelector('svg')
    expect(mark?.getAttribute('aria-hidden')).toBe('true')
    expect(mark?.querySelector('path')).toBeTruthy()
    // the hot cell is a light paper card, not a solid vermilion block
    expect(cells[0].className).toContain('heat-hot')
    const hot = ruleBody(themeCss, '.heat-hot')
    expect(hot).toMatch(/background/)
    expect(hot).not.toMatch(/#b53632|var\(--link\)/i)
    expect(hot).not.toMatch(/color:\s*white/)
  })

  it('overview shows at most 3 red-pen marks (circles + wavy) with preview-like data', async () => {
    // same error counts as preview.tsx: q3 45%, q6 53%, q9 38%, q15 43% (of 40)
    const wrong = [3, 5, 18, 7, 2, 21, 9, 4, 15, 6, 1, 12, 8, 3, 17]
    const qs = wrong.map((n, i) => ({ ...question(String(i + 1), n), student_count: 40, answered_count: 40 }))
    const { container } = renderOverview(3, qs)
    await waitFor(() => expect(screen.getByText('第 15 题')).toBeTruthy())
    const marks = container.querySelectorAll('.red-circle, .red-wavy')
    expect(marks.length).toBeLessThanOrEqual(3)
    expect(container.querySelectorAll('.red-wavy')).toHaveLength(1)
    const cells = [...container.querySelectorAll('.q-cell')]
    const circled = cells.filter((c) => c.querySelector('.red-circle')).map((c) => c.querySelector('.qno')!.textContent)
    expect(circled).toEqual(['第 3 题', '第 6 题'])
    // q15 is still hot (light tile, vermilion number), just not circled
    expect(cells[14].className).toContain('heat-hot')
    expect(cells[14].querySelector('.red-circle')).toBeNull()
  })

  it('pending-review hint carries the red wavy underline', async () => {
    const { container } = renderOverview(3)
    await waitFor(() => expect(container.querySelector('.pending-hint')).toBeTruthy())
    const hint = container.querySelector('.pending-hint')!
    expect(hint.textContent).toBe('还有 3 项没复核，统计可能变化，请先复核')
    expect(hint.querySelector('.red-wavy')?.textContent).toBe('3 项没复核')
    expect(ruleBody(themeCss, '.red-wavy')).toMatch(/underline wavy/)
  })
})
