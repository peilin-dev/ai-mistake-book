import { describe, expect, it } from 'vitest'
import { previewRoster } from '../src/lib/roster'

// Same inputs as backend/tests/test_classes.py so both parsers stay in sync.
describe('previewRoster', () => {
  it('formats, blank lines and dedupe', () => {
    const r = previewRoster('张三\n 2024002 李四 \n王五,2024003\n\n张三')
    expect(r.count).toBe(3)
    expect(r.entries).toEqual([
      { name: '张三', studentNo: null },
      { name: '李四', studentNo: '2024002' },
      { name: '王五', studentNo: '2024003' },
    ])
  })
  it('full-width comma, tab, CRLF, letter prefix', () => {
    expect(previewRoster('赵六，2024004\r\nA2024005\t钱七\n   \n孙八\t2024006').entries).toEqual([
      { name: '赵六', studentNo: '2024004' },
      { name: '钱七', studentNo: 'A2024005' },
      { name: '孙八', studentNo: '2024006' },
    ])
  })
  it('non-number tokens stay in the name', () => {
    expect(previewRoster('张三 李四\nJohn Smith\n2024001 Mary Ann').entries).toEqual([
      { name: '张三 李四', studentNo: null },
      { name: 'John Smith', studentNo: null },
      { name: 'Mary Ann', studentNo: '2024001' },
    ])
  })
  it('two numbers or only a number: whole line is the name', () => {
    expect(previewRoster('1 2').entries).toEqual([{ name: '1 2', studentNo: null }])
    expect(previewRoster('2024001').entries).toEqual([{ name: '2024001', studentNo: null }])
  })
  it('empty input', () => {
    expect(previewRoster('')).toEqual({ count: 0, entries: [] })
  })
})
