import { describe, expect, it } from 'vitest'
import { classCardStatus } from '../src/lib/classCard'
import type { AssignmentOut, ProgressOut } from '../src/lib/types'

const a = { id: 1, class_id: 1, subject: 'math', title: '单元测验', answer_key_status: 'none', has_answer_key: false } as AssignmentOut
const p = (o: Partial<ProgressOut>): ProgressOut => ({
  total: 0, queued: 0, processing: 0, done: 0, failed: 0, needs_review: 0, ...o,
})

describe('classCardStatus', () => {
  it('no assignment yet', () => {
    expect(classCardStatus(null, null)).toEqual({ text: '还没有作业', tone: 'gray' })
  })
  it('progress unavailable', () => {
    expect(classCardStatus(a, null)).toEqual({ text: '', tone: 'gray' })
  })
  it('nothing photographed yet', () => {
    expect(classCardStatus(a, p({}))).toEqual({ text: '还没拍卷', tone: 'gray' })
  })
  it('needs review wins', () => {
    expect(classCardStatus(a, p({ total: 3, done: 3, needs_review: 4 }))).toEqual({ text: '4 题待复核', tone: 'warn' })
    expect(classCardStatus(a, p({ total: 3, queued: 1, done: 2, needs_review: 1 }))).toEqual({ text: '1 题待复核', tone: 'warn' })
  })
  it('grading in progress', () => {
    expect(classCardStatus(a, p({ total: 5, queued: 1, processing: 1, done: 3 }))).toEqual({ text: '批改中 3/5', tone: 'busy' })
  })
  it('all done', () => {
    expect(classCardStatus(a, p({ total: 3, done: 2, failed: 1 }))).toEqual({ text: '全部完成', tone: 'ok' })
  })
})
