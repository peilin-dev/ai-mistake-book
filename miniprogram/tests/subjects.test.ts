import { describe, expect, it } from 'vitest'
import { subjectsForGrade } from '../src/lib/subjects'

describe('subjectsForGrade', () => {
  it('grades 1-6', () => {
    const s = subjectsForGrade(6)
    expect(s.map((x) => x.value)).toEqual(['chinese', 'math', 'english', 'science', 'politics', 'other'])
    expect(s.map((x) => x.label)).toEqual(['语文', '数学', '英语', '科学', '道德与法治', '其他'])
    expect(s.some((x) => x.label === '物理')).toBe(false)
    expect(subjectsForGrade(1)).toEqual(s)
  })
  it('grades 7-9 add five more', () => {
    const s = subjectsForGrade(7)
    expect(s.map((x) => x.value)).toEqual([
      'chinese', 'math', 'english', 'science', 'politics', 'other',
      'physics', 'chemistry', 'biology', 'history', 'geography',
    ])
    expect(s.find((x) => x.value === 'physics')?.label).toBe('物理')
    expect(subjectsForGrade(9)).toEqual(s)
  })
})
