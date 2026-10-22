import type { AnalyticsOut, HistoryItem, QuestionStatOut } from './types'

export const AI_LABEL = 'AI 推测'

/** 0.714 -> "71%"; null -> "—". */
export function percent(x: number | null): string {
  return x === null || x === undefined ? '—' : `${Math.round(x * 100)}%`
}

export function overviewNotices(a: AnalyticsOut): { text: string; action: 'review' | null }[] {
  const out: { text: string; action: 'review' | null }[] = []
  if (a.pending_review > 0) out.push({ text: `还有 ${a.pending_review} 题待复核，统计可能不准`, action: 'review' })
  if (a.pages_not_counted > 0) {
    out.push({ text: `还有 ${a.pages_not_counted} 张卷子没批完或没认出学生，统计暂未包含`, action: null })
  }
  return out
}

export function questionLine(q: QuestionStatOut): string {
  const base = `正确率 ${percent(q.accuracy)}`
  if (q.is_subjective || !q.top_wrong_answer) return base
  return `${base} · 最常见错答「${q.top_wrong_answer}」`
}

/** "10-22 作业　9 / 14 分（64%）"; just the score when there is no full mark. */
export function historyLine(h: HistoryItem): string {
  if (!h.max_score) return `${h.title}　${h.score} 分`
  return `${h.title}　${h.score} / ${h.max_score} 分（${percent(h.score / h.max_score)}）`
}

export function needsSignature(me: { display_name: string | null }): boolean {
  return !me.display_name || !me.display_name.trim()
}
