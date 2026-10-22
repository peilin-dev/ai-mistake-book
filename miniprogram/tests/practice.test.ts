import { describe, expect, it } from 'vitest'
import { FAILED_TEXT, PARTIAL_TEXT, failedReplace, generatedAtText, isWorking, optionLetter, progressText, sourceLabel } from '../src/lib/practice'
import type { PracticeItemOut, PracticePaperOut } from '../src/lib/types'

const item = (o: Partial<PracticeItemOut> = {}): PracticeItemOut => ({
  id: 1, position: 1, source_no: '5', knowledge_point: null, kind: 'choice',
  stem: 's', options: null, answer: 'A', replacing: false, ...o,
})
const paper = (o: Partial<PracticePaperOut> = {}): PracticePaperOut => ({
  id: 1, scope: 'class', student_name: null, status: 'done', partial: false,
  sources_total: 5, sources_done: 5, error: null, generated_at: null,
  last_replace_failed_item: null, items: [item()], ...o,
})

describe('progressText', () => {
  it('shows counts while running', () => {
    expect(progressText(paper({ status: 'running', sources_done: 2 }))).toBe('正在出题…（已完成 2 / 5 道源题）')
  })
  it('queued with nothing done has no counts', () => {
    expect(progressText(paper({ status: 'queued', sources_done: 0 }))).toBe('正在出题…')
  })
  it('queued with progress shows counts', () => {
    expect(progressText(paper({ status: 'queued', sources_done: 1 }))).toBe('正在出题…（已完成 1 / 5 道源题）')
  })
})

describe('isWorking', () => {
  it('true for queued and running', () => {
    expect(isWorking(paper({ status: 'queued' }))).toBe(true)
    expect(isWorking(paper({ status: 'running' }))).toBe(true)
  })
  it('true when any item is replacing', () => {
    expect(isWorking(paper({ items: [item(), item({ id: 2, replacing: true })] }))).toBe(true)
  })
  it('false when done and idle', () => {
    expect(isWorking(paper())).toBe(false)
    expect(isWorking(paper({ status: 'failed', items: [] }))).toBe(false)
  })
})

describe('sourceLabel', () => {
  it('plain label', () => {
    expect(sourceLabel(item())).toBe('第 5 题的同类题')
  })
  it('adds knowledge point', () => {
    expect(sourceLabel(item({ knowledge_point: '一元二次方程' }))).toBe('第 5 题的同类题 · 一元二次方程')
  })
  it('ignores blank knowledge point', () => {
    expect(sourceLabel(item({ knowledge_point: '  ' }))).toBe('第 5 题的同类题')
  })
})

describe('optionLetter and texts', () => {
  it('letters', () => {
    expect(optionLetter(0)).toBe('A')
    expect(optionLetter(3)).toBe('D')
  })
  it('texts', () => {
    expect(PARTIAL_TEXT).toBe('部分题目没出成，可以重新生成')
    expect(FAILED_TEXT).toBe('这次没出成题，请稍后重试')
  })
})

describe('generatedAtText', () => {
  it('converts naive UTC to local time', () => {
    const d = new Date(Date.UTC(2026, 9, 22, 8, 5))
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const expected = `${d.getMonth() + 1}月${d.getDate()}日 ${hh}:${mm}`
    expect(generatedAtText('2026-10-22T08:05:00')).toBe(expected)
    expect(generatedAtText('2026-10-22T08:05:00.123456')).toBe(expected)
  })
  it('is empty for null or garbage', () => {
    expect(generatedAtText(null)).toBe('')
    expect(generatedAtText('soon')).toBe('')
  })
})

describe('failedReplace', () => {
  const flagged = (replacing: boolean) =>
    paper({ last_replace_failed_item: 7, items: [item({ id: 7, replacing })] })
  it('reports an asked item that stopped replacing and is flagged', () => {
    expect(failedReplace([7], flagged(false))).toBe(7)
  })
  it('ignores items not asked about or still replacing', () => {
    expect(failedReplace([8], flagged(false))).toBeNull()
    expect(failedReplace([7], flagged(true))).toBeNull()
    expect(failedReplace([7], paper())).toBeNull()
  })
})
