import type { ReviewOut, ReviewQuestion } from './types'

export type ReviewItem =
  | { kind: 'page'; key: string; pageId: number; imageUrl: string | null; recognizedName: string | null }
  | { kind: 'question'; key: string; question: ReviewQuestion }

/** Unrecognised-student pages first, then questions; backend order is kept. */
export function buildQueue(r: ReviewOut): ReviewItem[] {
  return [
    ...r.pages_unassigned.map(
      (p): ReviewItem => ({
        kind: 'page',
        key: `p${p.page_id}`,
        pageId: p.page_id,
        imageUrl: p.image_url,
        recognizedName: p.recognized_name,
      }),
    ),
    ...r.questions.map((question): ReviewItem => ({ kind: 'question', key: `q${question.id}`, question })),
  ]
}

export function reasonText(reason: ReviewQuestion['reason']): string {
  switch (reason) {
    case 'low_confidence':
      return 'AI 不太确定'
    case 'answer_mismatch':
      return '和全班多数答案不一致'
    default:
      return '学生不确定'
  }
}

/** A typed score if it is a number in 0..max (any non-negative when max is unknown), else null. */
export function parseScore(text: string, max: number | null): number | null {
  const t = text.trim()
  if (t === '') return null
  const n = Number(t)
  if (!Number.isFinite(n) || n < 0) return null
  if (max !== null && n > max) return null
  return n
}

/**
 * Signed image URLs expire. On an image error the page calls the returned function: it refetches
 * the review queue and returns the same item with fresh URLs. Each item is refreshed at most once
 * (a second failure means the image is really broken, so we stop); null means "give up".
 */
export function refreshesExpiredImageUrls(
  fetchReview: () => Promise<ReviewOut>,
): (item: ReviewItem) => Promise<ReviewItem | null> {
  const tried = new Set<string>()
  return async (item) => {
    if (tried.has(item.key)) return null
    tried.add(item.key)
    try {
      const fresh = buildQueue(await fetchReview())
      return fresh.find((i) => i.key === item.key) ?? null
    } catch {
      return null
    }
  }
}
