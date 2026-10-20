import { describe, expect, it } from 'vitest'
import { GRADE_LABELS, defaultClassName } from '../src/lib/grades'

describe('grades', () => {
  it('offers exactly grades 1-9', () => {
    expect(GRADE_LABELS).toHaveLength(9)
    expect(GRADE_LABELS[0]).toBe('一年级')
    expect(GRADE_LABELS[8]).toBe('九年级')
  })
  it('default class name follows grade', () => {
    expect(defaultClassName(5)).toBe('五年级1班')
    expect(defaultClassName(9)).toBe('九年级1班')
  })
})
