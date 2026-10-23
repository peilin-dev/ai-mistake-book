import { describe, expect, it } from 'vitest'
import { blankRow, toPutBody, validateRows } from '../src/lib/answerKey'
import { mergeKeys } from '../src/lib/answerKeyMerge'
import { canRetry, pageStatusText, type PageItem } from '../src/lib/pages'
import { nextIndex } from '../src/lib/claim'
import { scoreError } from '../src/lib/results'
describe('teacher work rules', () => {
  it('shows pending, processing, failure and unclaimed states', () => {
    const p = {
      status: 'queued',
      student_id: null,
      fail_reason: null,
    } as PageItem
    expect(pageStatusText(p)).toBe('排队中')
    expect(pageStatusText({ ...p, status: 'processing' })).toBe('批改中')
    expect(pageStatusText({ ...p, status: 'done' })).toBe('待认领')
    expect(pageStatusText({ ...p, status: 'done', student_id: 2 })).toBe('完成')
    expect(
      pageStatusText({
        ...p,
        status: 'failed',
        fail_reason: 'model_unavailable',
      }),
    ).toContain('可以重试')
    expect(
      canRetry({ ...p, status: 'failed', fail_reason: 'unreadable' }),
    ).toBe(false)
  })
  it('merges answers in page order even when a previous page is retried later', () => {
    const item = {
      question_no: '1',
      answer: 'A',
      max_score: 2,
      is_subjective: false,
    }
    const result = mergeKeys([
      { pageIndex: 2, items: [{ ...item, answer: 'C' }] },
      { pageIndex: 0, items: [item] },
    ])
    expect(result.items[0].answer).toBe('C')
    expect(result.overridden).toEqual(['1'])
  })
  it('rejects duplicate numbers and invalid scores before confirmation', () => {
    const first = {
      ...blankRow(),
      question_no: '1',
      answer: 'A',
      max_score: '-1',
    }
    expect(validateRows([first])).toContain('分值')
    first.max_score = '2'
    expect(validateRows([first, { ...first, key: 'second' }])).toContain('重复')
    expect(toPutBody([first]).items[0].max_score).toBe(2)
  })
  it('validates corrections against printed score limits', () => {
    expect(scoreError('', 5)).toBeTruthy()
    expect(scoreError('6', 5)).toBeTruthy()
    expect(scoreError('NaN', null)).toBeTruthy()
    expect(scoreError('2.5', 5)).toBe('')
  })
  it('finishes claiming at the last page', () => {
    expect(nextIndex([3, 5], 3)).toBe(1)
    expect(nextIndex([3, 5], 5)).toBe(-1)
    expect(nextIndex([], 3)).toBe(-1)
  })
})
