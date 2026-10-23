import { describe, expect, it } from 'vitest'
import { errorRate, heatLevel, pendingHint } from '../src/lib/overview'

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

  it('pendingHint', () => {
    expect(pendingHint(0)).toBeNull()
    expect(pendingHint(3)).toBe('还有 3 项没复核，统计可能变化，请在手机上复核')
  })
})
