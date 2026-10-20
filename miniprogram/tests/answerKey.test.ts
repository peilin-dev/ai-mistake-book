import { describe, expect, it } from 'vitest'
import { blankRow, toPutBody, toRows, validateRows, type KeyRow } from '../src/lib/answerKey'

const row = (o: Partial<KeyRow> = {}): KeyRow => ({
  key: 'k',
  question_no: '1',
  answer: 'A',
  max_score: '',
  is_subjective: false,
  ...o,
})

describe('toRows', () => {
  it('turns server items into editable rows with string scores', () => {
    const rows = toRows([
      { question_no: '1', answer: 'A', max_score: 2.5, is_subjective: false },
      { question_no: '2', answer: '略', max_score: null, is_subjective: true },
    ])
    expect(rows.map((r) => [r.question_no, r.answer, r.max_score, r.is_subjective])).toEqual([
      ['1', 'A', '2.5', false],
      ['2', '略', '', true],
    ])
    expect(new Set(rows.map((r) => r.key)).size).toBe(2)
  })
})

describe('blankRow', () => {
  it('gives each new row a unique key', () => {
    expect(blankRow().key).not.toBe(blankRow().key)
  })
})

describe('validateRows', () => {
  it('accepts a good list', () => {
    expect(validateRows([row(), row({ key: 'b', question_no: '2' })])).toBeNull()
  })
  it('needs at least one row', () => {
    expect(validateRows([])).toBe('还没有题目，请先加一行')
  })
  it('rejects an empty question number and names the row', () => {
    expect(validateRows([row(), row({ key: 'b', question_no: '  ' })])).toBe('第 2 行没有填题号')
  })
  it('rejects duplicate question numbers, ignoring spaces', () => {
    expect(validateRows([row(), row({ key: 'b', question_no: ' 1 ' })])).toBe('题号 1 重复了，请改一下')
  })
  it('rejects a non-numeric or negative score', () => {
    expect(validateRows([row({ max_score: 'abc' })])).toBe('第 1 行的分值要填数字')
    expect(validateRows([row({ max_score: '-1' })])).toBe('第 1 行的分值要填数字')
  })
  it('allows an empty score', () => {
    expect(validateRows([row({ max_score: ' ' })])).toBeNull()
  })
})

describe('toPutBody', () => {
  it('trims, converts scores and keeps the subjective flag', () => {
    const body = toPutBody([
      row({ question_no: ' 1 ', answer: ' A ', max_score: '3' }),
      row({ key: 'b', question_no: '2', answer: '', max_score: '', is_subjective: true }),
    ])
    expect(body).toEqual({
      items: [
        { question_no: '1', answer: 'A', max_score: 3, is_subjective: false },
        { question_no: '2', answer: '', max_score: null, is_subjective: true },
      ],
    })
  })
})
