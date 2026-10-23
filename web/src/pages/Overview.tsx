import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Header from '../components/Header'
import { errorText, request } from '../lib/api'
import {
  avgText, dateText, errorRate, heatLevel, pendingHint, percent, subjectLabel,
  type Analytics, type AssignmentOut, type ClassOut,
} from '../lib/overview'

/** Projected in class: read-only, no download buttons except the single link to the downloads page. */
export default function Overview() {
  const { assignmentId } = useParams()
  const [assignment, setAssignment] = useState<AssignmentOut | null>(null)
  const [className, setClassName] = useState('')
  const [stats, setStats] = useState<Analytics | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setError('')
    setAssignment(null)
    setStats(null)
    setClassName('')
    Promise.all([
      request<AssignmentOut>('GET', `/api/assignments/${assignmentId}`),
      request<Analytics>('GET', `/api/assignments/${assignmentId}/analytics`),
      // only used for the heading; a failure must not hide the overview
      request<ClassOut[]>('GET', '/api/classes').catch(() => [] as ClassOut[]),
    ])
      .then(([a, s, classes]) => {
        if (!alive) return
        setAssignment(a)
        setStats(s)
        setClassName(classes.find((c) => c.id === a.class_id)?.name ?? '')
      })
      .catch((e) => alive && setError(errorText(e)))
    return () => {
      alive = false
    }
  }, [assignmentId])

  const hint = stats ? pendingHint(stats.pending_review) : null
  const heading = assignment
    ? [className, subjectLabel(assignment.subject), assignment.title, dateText(assignment.created_at)]
        .filter(Boolean)
        .join(' · ')
    : ''

  return (
    <>
      <Header />
      <main className="page overview">
        <Link to="/" className="back">← 返回班级</Link>
        {error && <p className="err">{error}</p>}
        {!error && !(assignment && stats) && <p className="empty">加载中…</p>}
        {assignment && stats && (
          <>
            <h1 className="main-title">{heading}</h1>
            <div className="stat-row">
              <div className="stat"><span className="num">{stats.counted_students} / {stats.roster_size}</span><span className="lbl">全班人数</span></div>
              <div className="stat"><span className="num">{avgText(stats.average_score)}</span><span className="lbl">平均分</span></div>
              <div className="stat"><span className="num">{percent(stats.pass_rate)}</span><span className="lbl">及格率</span></div>
              <Link className="dl-link" to={`/a/${assignmentId}/downloads`}>下载打印</Link>
            </div>
            {hint && <p className="pending-hint">{hint}</p>}
            {stats.questions.length === 0 ? (
              <p className="empty">还没有错题数据</p>
            ) : (
              <div className="q-grid">
                {stats.questions.map((q) => {
                  const rate = errorRate(q)
                  return (
                    <Link
                      key={q.question_no}
                      to={`/a/${assignmentId}/q/${encodeURIComponent(q.question_no)}`}
                      className={`q-cell heat-${heatLevel(rate)}`}
                    >
                      <span className="qno">{q.question_no}</span>
                      <span className="qpct">{percent(rate)}</span>
                      {q.is_subjective && <span className="qsub">主观</span>}
                    </Link>
                  )
                })}
              </div>
            )}
          </>
        )}
      </main>
    </>
  )
}
