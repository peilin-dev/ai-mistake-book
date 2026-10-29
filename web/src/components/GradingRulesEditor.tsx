import { useEffect, useState } from 'react'
import { request, errorText } from '../lib/api'
import { gradingRules } from '../lib/gradingRules'

export interface AssignmentContext { title?: string; class_id?: number; subject: string }
export default function GradingRulesEditor({ assignmentId, onAssignment }: { assignmentId: string; onAssignment?: (assignment: AssignmentContext) => void }) {
  const [subject, setSubject] = useState(''), [rules, setRules] = useState('')
  const [loaded, setLoaded] = useState(false), [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(''), [error, setError] = useState('')
  useEffect(() => {
    let live = true
    request<AssignmentContext & { grading_rules?: string | null }>('GET', `/api/assignments/${assignmentId}`)
      .then(a => { if (live) { setSubject(a.subject); setRules(a.grading_rules || ''); setLoaded(true); onAssignment?.(a) } })
      .catch(e => live && setError(errorText(e)))
    return () => { live = false }
  }, [assignmentId, onAssignment])
  return <details className="grading-rules-editor">
    <summary>本次作业的批改规则与评分细则</summary>
    <p className="hint">{gradingRules[subject] || '正在读取学科规则…'}</p>
    <label>老师补充的评分细则（优先使用）
      <textarea disabled={!loaded || busy} maxLength={6000} rows={5} value={rules} onChange={e => { setRules(e.target.value); setMessage('') }} placeholder="例如：第 3 题列式 2 分、计算 2 分、单位 1 分；允许等价解法。作文可填写评分维度及各项分值。" />
    </label>
    <p className="hint">具体题目的分值和参考答案请在下方核对。未指定的主观题细则由 AI 建议，老师需复核。保存后的规则用于后续批改，不会自动重算已有成绩。</p>
    <button disabled={!loaded || busy} onClick={async () => {
      setBusy(true); setError('')
      try { await request('PATCH', `/api/assignments/${assignmentId}/grading-rules`, { grading_rules: rules.trim() || null }); setMessage('评分细则已保存') }
      catch (e) { setError(errorText(e)) }
      finally { setBusy(false) }
    }}>{busy ? '保存中…' : '保存评分细则'}</button>
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" className="err">{error}</p>}
  </details>
}
