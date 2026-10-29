import { afterEach, expect, it } from 'vitest'
import { setAnswerKeyDraft, takeAnswerKeyDraft } from '../src/lib/answerKeyDraft'
const items = [{ question_no: '1', answer: 'A', max_score: null, is_subjective: false }]
afterEach(() => { takeAnswerKeyDraft(1) })
it('hands the preview to the editor once', () => {
 setAnswerKeyDraft(1, items)
 expect(takeAnswerKeyDraft(1)).toEqual(items)
 expect(takeAnswerKeyDraft(1)).toBeUndefined()
})
it('does not carry previews into another assignment', () => {
 setAnswerKeyDraft(1, items)
 expect(takeAnswerKeyDraft(2)).toBeUndefined()
 expect(takeAnswerKeyDraft(1)).toBeUndefined()
})
