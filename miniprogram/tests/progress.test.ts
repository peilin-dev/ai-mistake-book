import { describe, expect, it } from 'vitest'
import { isFinished, progressText } from '../src/lib/progress'
import type { ProgressOut, SubmissionOut } from '../src/lib/types'

const p = (o: Partial<ProgressOut>): ProgressOut => ({
  total: 0, queued: 0, processing: 0, done: 0, failed: 0, needs_review: 0, ...o,
})

describe('isFinished', () => {
  it('false when nothing uploaded', () => expect(isFinished(p({}))).toBe(false))
  it('false while queued or processing', () => {
    expect(isFinished(p({ total: 3, queued: 1, done: 2 }))).toBe(false)
    expect(isFinished(p({ total: 3, processing: 1, done: 2 }))).toBe(false)
  })
  it('true when all done or failed', () => {
    expect(isFinished(p({ total: 3, done: 2, failed: 1 }))).toBe(true)
  })
})

describe('progressText', () => {
  it('formats pages and students', () => {
    const subs = [{ id: 1 }, { id: 2 }] as SubmissionOut[]
    expect(progressText(p({ total: 5, done: 3, failed: 1, queued: 1 }), subs, 40)).toEqual({
      pages: '已批 3/5 张',
      students: '已出成绩 2/40 人',
    })
  })
  it('zero state', () => {
    expect(progressText(p({}), [], 0)).toEqual({ pages: '已批 0/0 张', students: '已出成绩 0/0 人' })
  })
})
