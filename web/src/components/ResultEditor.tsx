import { useRef, useState } from 'react'
import { errorText, request } from '../lib/api'
import { scoreError, type QuestionResult } from '../lib/results'
export default function ResultEditor({
  question,
  onSaved,
}: {
  question: QuestionResult
  onSaved: (r: QuestionResult) => void
}) {
  const [score, setScore] = useState(String(question.score)),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const lock = useRef(false)
  async function save(body: { score?: number; is_correct?: boolean }) {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setError('')
    try {
      const r = await request<QuestionResult>(
        'PATCH',
        `/api/question-results/${question.id}`,
        body,
      )
      onSaved(r)
      setScore(String(r.score))
    } catch (e) {
      setError(errorText(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  return (
    <div className="result-editor">
      <div className="work-actions">
        <label>
          得分
          <input
            aria-label={`第 ${question.question_no} 题得分`}
            type="number"
            min="0"
            max={question.max_score ?? undefined}
            step="any"
            value={score}
            onChange={(e) => setScore(e.target.value)}
          />
        </label>
        <span>/ {question.max_score ?? '未标分值'}</span>
        <button
          disabled={busy}
          onClick={() => {
            const invalid = scoreError(score, question.max_score)
            if (invalid) setError(invalid)
            else void save({ score: Number(score) })
          }}
        >
          保存分数
        </button>
        <button
          disabled={busy || question.max_score === null}
          onClick={() => void save({ is_correct: true })}
        >
          判对
        </button>
        <button
          disabled={busy}
          onClick={() => void save({ is_correct: false })}
        >
          判错
        </button>
        <button
          className="btn-primary"
          disabled={busy}
          onClick={() =>
            void save({
              score: question.score,
              is_correct: question.is_correct,
            })
          }
        >
          确认原判
        </button>
      </div>
      {question.max_score === null && (
        <p className="hint">原卷没有标分值，请填写得分或确认原判。</p>
      )}
      {error && (
        <p className="err" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
