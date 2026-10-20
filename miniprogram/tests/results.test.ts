import { describe, expect, it } from 'vitest'
import { NO_ANSWER_KEY_BANNER, scoreText, verdictText } from '../src/lib/results'

describe('results text', () => {
  it('banner copy', () => expect(NO_ANSWER_KEY_BANNER).toBe('本次没有答案卷，答案由 AI 判断'))
  it('verdict', () => {
    expect(verdictText({ is_correct: true })).toBe('对')
    expect(verdictText({ is_correct: false })).toBe('错')
    expect(verdictText({ is_correct: null })).toBe('没判出')
  })
  it('score', () => {
    expect(scoreText({ score: 2, max_score: 4 })).toBe('2 / 4 分')
    expect(scoreText({ score: 2, max_score: null })).toBe('2 分')
    expect(scoreText({ score: null, max_score: 4 })).toBe('')
  })
})
