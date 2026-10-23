import { describe, expect, it } from 'vitest'
import { circledQuestions, errorRate, heatLevel, pendingHint } from '../src/lib/overview'

describe('overview helpers', () => {
  it('errorRate handles zero', () => {
    expect(errorRate({ wrong_count: 0, student_count: 0 })).toBeNull()
    expect(errorRate({ wrong_count: 3, student_count: 0 })).toBeNull()
    expect(errorRate({ wrong_count: 3, student_count: 12 })).toBe(0.25)
    expect(errorRate({ wrong_count: 0, student_count: 10 })).toBe(0)
  })

  it('heatLevel thresholds 0.4 and 0.2', () => {
    expect(heatLevel(null)).toBe('none')
    expect(heatLevel(0.4)).toBe('hot')
    expect(heatLevel(0.39)).toBe('warm')
    expect(heatLevel(0.2)).toBe('warm')
    expect(heatLevel(0.19)).toBe('cool')
    expect(heatLevel(0)).toBe('cool')
  })

  const q = (no: string, wrong: number, n = 10) => ({ question_no: no, wrong_count: wrong, student_count: n })

  it('circledQuestions: none >= 40% -> only the worst one', () => {
    expect([...circledQuestions([q('1', 1), q('2', 3), q('3', 2)])]).toEqual(['2'])
  })

  it('circledQuestions: five >= 40% -> only the top 2, ties in question order', () => {
    const qs = [q('1', 4), q('2', 6), q('3', 5), q('4', 6), q('5', 4)]
    expect([...circledQuestions(qs)].sort()).toEqual(['2', '4'])
    expect([...circledQuestions([q('1', 5), q('2', 5), q('3', 5)])].sort()).toEqual(['1', '2'])
  })

  it('circledQuestions: all zero (or no rows) -> none', () => {
    expect(circledQuestions([q('1', 0), q('2', 0), q('3', 0, 0)]).size).toBe(0)
    expect(circledQuestions([]).size).toBe(0)
  })

  it('pendingHint', () => {
    expect(pendingHint(0)).toBeNull()
    expect(pendingHint(3)).toBe('还有 3 项没复核，统计可能变化，请在手机上复核')
  })
})
