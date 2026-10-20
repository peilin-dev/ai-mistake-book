import { describe, expect, it, vi } from 'vitest'
import { buildQueue, parseScore, reasonText, refreshesExpiredImageUrls } from '../src/lib/review'
import type { ReviewOut, ReviewQuestion } from '../src/lib/types'

const q = (id: number, o: Partial<ReviewQuestion> = {}): ReviewQuestion => ({
  id,
  question_no: String(id),
  question_text: 't',
  student_answer: 'a',
  correct_answer: 'b',
  is_correct: false,
  score: 0,
  max_score: 2,
  confidence: 0.5,
  student_name: '张三',
  reason: 'low_confidence',
  crop_url: `crop${id}`,
  page_id: 1,
  recognized_name: '张三',
  image_url: 'page1',
  ...o,
})

const review = (o: Partial<ReviewOut> = {}): ReviewOut => ({
  pages_unassigned: [{ page_id: 9, image_url: 'p9', recognized_name: '李' }],
  questions: [q(1), q(2)],
  ...o,
})

describe('buildQueue', () => {
  it('puts unassigned pages first, keeps backend order', () => {
    const items = buildQueue(review({ pages_unassigned: [
      { page_id: 9, image_url: 'p9', recognized_name: '李' },
      { page_id: 4, image_url: null, recognized_name: null },
    ] }))
    expect(items.map((i) => i.kind)).toEqual(['page', 'page', 'question', 'question'])
    expect(items.map((i) => i.key)).toEqual(['p9', 'p4', 'q1', 'q2'])
  })
  it('is empty when nothing to review', () => {
    expect(buildQueue({ pages_unassigned: [], questions: [] })).toEqual([])
  })
})

describe('reasonText', () => {
  it('covers all reasons', () => {
    expect(reasonText('student_uncertain')).toBe('学生不确定')
    expect(reasonText('low_confidence')).toBe('AI 不太确定')
    expect(reasonText('answer_mismatch')).toBe('和全班多数答案不一致')
  })
})

describe('parseScore', () => {
  it('accepts 0..max', () => {
    expect(parseScore('0', 4)).toBe(0)
    expect(parseScore('2.5', 4)).toBe(2.5)
    expect(parseScore('4', 4)).toBe(4)
  })
  it('rejects out of range, empty, non-numeric', () => {
    expect(parseScore('5', 4)).toBeNull()
    expect(parseScore('-1', 4)).toBeNull()
    expect(parseScore('', 4)).toBeNull()
    expect(parseScore('abc', 4)).toBeNull()
  })
  it('allows any non-negative score when max is unknown', () => {
    expect(parseScore('100', null)).toBe(100)
    expect(parseScore('-1', null)).toBeNull()
  })
})

describe('refreshesExpiredImageUrls', () => {
  it('refetches once and returns the item with fresh URLs', async () => {
    const fetchReview = vi.fn().mockResolvedValue(
      review({ questions: [q(1, { crop_url: 'new-crop', image_url: 'new-page' })] }),
    )
    const refresh = refreshesExpiredImageUrls(fetchReview)
    const item = buildQueue(review())[1]
    const fresh = await refresh(item)
    expect(fetchReview).toHaveBeenCalledTimes(1)
    expect(fresh).toMatchObject({ kind: 'question', key: 'q1' })
    expect(fresh && fresh.kind === 'question' && fresh.question.crop_url).toBe('new-crop')
  })
  it('refreshes a page item', async () => {
    const refresh = refreshesExpiredImageUrls(async () =>
      review({ pages_unassigned: [{ page_id: 9, image_url: 'fresh', recognized_name: '李' }] }),
    )
    const fresh = await refresh(buildQueue(review())[0])
    expect(fresh && fresh.kind === 'page' && fresh.imageUrl).toBe('fresh')
  })
  it('only once per item, even when the first refetch failed', async () => {
    const fetchReview = vi.fn().mockRejectedValue(new Error('net'))
    const refresh = refreshesExpiredImageUrls(fetchReview)
    const item = buildQueue(review())[1]
    expect(await refresh(item)).toBeNull()
    expect(await refresh(item)).toBeNull()
    expect(fetchReview).toHaveBeenCalledTimes(1)
  })
  it('does not loop when the fresh URL fails again', async () => {
    const fetchReview = vi.fn().mockResolvedValue(review())
    const refresh = refreshesExpiredImageUrls(fetchReview)
    const item = buildQueue(review())[1]
    expect(await refresh(item)).not.toBeNull()
    expect(await refresh(item)).toBeNull()
    expect(fetchReview).toHaveBeenCalledTimes(1)
  })
  it('returns null when the item is gone from the queue; other items still get one try', async () => {
    const fetchReview = vi.fn().mockResolvedValue(review({ questions: [q(2)] }))
    const refresh = refreshesExpiredImageUrls(fetchReview)
    const items = buildQueue(review())
    expect(await refresh(items[1])).toBeNull()
    expect(await refresh(items[2])).not.toBeNull()
    expect(fetchReview).toHaveBeenCalledTimes(2)
  })
})
