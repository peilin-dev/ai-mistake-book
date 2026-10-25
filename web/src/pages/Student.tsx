import PaperComparison, { type PaperPage } from '../components/PaperComparison'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import { request, errorText } from '../lib/api'
import type { QuestionResult, Submission } from '../lib/results'
import { openViewerTab } from '../lib/download'
interface Detail extends Submission {
  pages?: PaperPage[]
  questions: QuestionResult[]
}
interface History {
  assignment_id: number
  title: string
  score: number
  max_score: number | null
  ratio: number | null
}
export default function Student() {
  const { assignmentId, submissionId } = useParams()
  const [data, setData] = useState<Detail>(),
    [history, setHistory] = useState<History[]>([]),
    [summary, setSummary] = useState<string | null>(),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [answers, setAnswers] = useState(true)
  const lock = useRef(false)
  useEffect(() => {
    let live = true
    setData(undefined); setHistory([]); setSummary(undefined); setError('')
    Promise.all([
      request<Detail>('GET', `/api/submissions/${submissionId}`),
      request<History[]>('GET', `/api/submissions/${submissionId}/history`),
    ])
      .then(([s, h]) => {
        if (live) {
          setData(s)
          setHistory(h)
        }
      })
      .catch((e) => live && setError(errorText(e)))
    return () => {
      live = false
    }
  }, [submissionId])
  async function exportPdf(kind: string) {
    if (lock.current) return
    const win = openViewerTab()
    if (!win) return setError('请允许浏览器打开新窗口后重试')
    lock.current = true
    setBusy(true)
    setError('')
    try {
      const r = await request<{ url: string }>(
        'POST',
        `/api/assignments/${assignmentId}/exports`,
        { kind, submission_id: Number(submissionId), include_answers: answers },
      )
      win.location.href = r.url
    } catch (e) {
      win.close()
      setError(errorText(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  return (
    <WorkShell
      title={data ? `${data.student_name} · 作答详情` : '学生作答详情'}
      description="含学生个人成绩，请勿投影此页。"
    >
      {error && (
        <p role="alert" className="err">
          {error}
        </p>
      )}
      {!data && !error && <p className="empty">加载中…</p>}
      {data && (
        <>
          <p>
            当前总分 {data.total_score} · 待复核 {data.needs_review_count} 项
          </p>
          <PaperComparison questions={data.questions} pages={data.pages} onSaved={async () => {
            const [fresh, h] = await Promise.all([
              request<Detail>('GET', `/api/submissions/${submissionId}`),
              request<History[]>('GET', `/api/submissions/${submissionId}/history`),
            ])
            setData(fresh); setHistory(h); setSummary(undefined)
          }} />
          <div className="work-actions">
            <Link to={`/a/${assignmentId}/grades`}>返回成绩表</Link>
            <button disabled={busy} onClick={() => void exportPdf('student')}>
              查看 / 打印个人错题单
            </button>
            <Link to={`/a/${assignmentId}/students/${submissionId}/practice`}>
              生成个人练习卷
            </Link>
            <label>
              <input
                type="checkbox"
                checked={answers}
                onChange={(e) => setAnswers(e.target.checked)}
              />
              练习卷附答案
            </label>
            <button
              disabled={busy}
              onClick={() => void exportPdf('practice_student')}
            >
              查看 / 打印个人练习卷
            </button>
          </div>
          <section className="notice">
            <h2 className="serif">
              学习小结 <small>AI 推测</small>
            </h2>
            {summary !== undefined && (
              <p>{summary || '暂时没能生成小结，请稍后重试。'}</p>
            )}
            <button
              disabled={busy}
              onClick={async () => {
                if (lock.current) return
                lock.current = true
                setBusy(true)
                setError('')
                try {
                  const r = await request<{ summary: string | null }>(
                    'POST',
                    `/api/submissions/${submissionId}/summary`,
                  )
                  setSummary(r.summary)
                } catch (e) {
                  setError(errorText(e))
                } finally {
                  lock.current = false
                  setBusy(false)
                }
              }}
            >
              {busy ? '正在处理…' : '生成学习小结'}
            </button>
          </section>
          <h2 className="serif">同班同学科历次成绩</h2>
          <div className="table-scroll">
            <table className="work-table">
              <thead>
                <tr>
                  <th>作业</th>
                  <th>得分 / 总分</th>
                  <th>得分率</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.assignment_id}>
                    <td>{h.title}</td>
                    <td>
                      {h.score} / {h.max_score ?? '未标分值'}
                    </td>
                    <td>
                      {h.ratio === null ? '—' : `${Math.round(h.ratio * 100)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </WorkShell>
  )
}
