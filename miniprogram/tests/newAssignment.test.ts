import { describe, expect, it } from 'vitest'
import { defaultAssignmentTitle, defaultSubject } from '../src/lib/newAssignment'
import { subjectsForGrade } from '../src/lib/subjects'

describe('defaultSubject', () => {
  const primary = subjectsForGrade(3)
  it('uses last subject when listed', () => {
    expect(defaultSubject(primary, 'english')).toBe('english')
  })
  it('falls back to first when last subject is not offered for this grade', () => {
    expect(defaultSubject(primary, 'physics')).toBe('chinese')
  })
  it('falls back to first when there is no last subject', () => {
    expect(defaultSubject(primary, null)).toBe('chinese')
    expect(defaultSubject(primary, undefined)).toBe('chinese')
  })
  it('keeps physics for a junior-high class', () => {
    expect(defaultSubject(subjectsForGrade(8), 'physics')).toBe('physics')
  })
})

describe('defaultAssignmentTitle', () => {
  it('pads month and day', () => {
    expect(defaultAssignmentTitle(new Date(2026, 0, 5))).toBe('01-05 作业')
  })
  it('two-digit values', () => {
    expect(defaultAssignmentTitle(new Date(2026, 9, 21))).toBe('10-21 作业')
  })
})
