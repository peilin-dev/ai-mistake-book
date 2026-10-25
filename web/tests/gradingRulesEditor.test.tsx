import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import GradingRulesEditor from '../src/components/GradingRulesEditor'
import { request } from '../src/lib/api'
vi.mock('../src/lib/api', async () => ({ ...await vi.importActual('../src/lib/api'), request: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
it('loads subject rules and saves a teacher override without regrading', async () => {
  vi.mocked(request).mockResolvedValue({ subject: 'chemistry', grading_rules: '配平1分' })
  render(<GradingRulesEditor assignmentId="7" />)
  fireEvent.click(screen.getByText('本次作业的批改规则与评分细则'))
  const input = await screen.findByDisplayValue('配平1分')
  expect(screen.getByText(/化学式、配平、条件/)).toBeTruthy()
  fireEvent.change(input, { target: { value: '配平2分，条件1分' } })
  fireEvent.click(screen.getByRole('button', { name: '保存评分细则' }))
  await waitFor(() => expect(request).toHaveBeenCalledWith('PATCH', '/api/assignments/7/grading-rules', { grading_rules: '配平2分，条件1分' }))
  expect((await screen.findByRole('status')).textContent).toContain('评分细则已保存')
})
