import { describe, expect, it } from 'vitest'
import { cropsByGroup, neighbors } from '../src/lib/question'

describe('cropsByGroup', () => {
  it('matches by submission_id and drops strays', () => {
    const groups = [
      { key: 'a', answer: '3', count: 2, students: [{ submission_id: 1 }, { submission_id: 2 }] },
      { key: 'b', answer: '4', count: 1, students: [{ submission_id: 3 }] },
    ]
    const crops = [
      { submission_id: 3, crop_url: '/c3' },
      { submission_id: 1, crop_url: '/c1' },
      { submission_id: 99, crop_url: '/stray' },
      { submission_id: 2, crop_url: '/c2' },
    ]
    const m = cropsByGroup(groups, crops)
    expect(m.get('a')).toEqual(['/c1', '/c2'])
    expect(m.get('b')).toEqual(['/c3'])
    expect([...m.values()].flat()).not.toContain('/stray')
  })
})

describe('neighbors', () => {
  it('at both ends', () => {
    expect(neighbors(['1', '2', '3'], '1')).toEqual({ prev: null, next: '2' })
    expect(neighbors(['1', '2', '3'], '3')).toEqual({ prev: '2', next: null })
    expect(neighbors(['1', '2', '3'], '2')).toEqual({ prev: '1', next: '3' })
    expect(neighbors(['1', '2'], 'x')).toEqual({ prev: null, next: null })
  })
})
