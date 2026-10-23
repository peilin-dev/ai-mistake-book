import type { AnswerKeyItem } from './answerKey'
export function mergeKeys(
  pages: { pageIndex: number; items: AnswerKeyItem[] }[],
) {
  const items = new Map<string, AnswerKeyItem>(),
    overridden = new Set<string>()
  for (const page of [...pages].sort((a, b) => a.pageIndex - b.pageIndex))
    for (const item of page.items) {
      if (items.has(item.question_no)) overridden.add(item.question_no)
      items.set(item.question_no, item)
    }
  return { items: [...items.values()], overridden: [...overridden] }
}
