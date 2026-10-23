import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Header from '../components/Header'
import Icon from '../components/Icon'
import RedCircle from '../components/RedCircle'
import { errorText, request } from '../lib/api'
import {
  avgText, circledQuestions, dateText, errorRate, heatLevel, pendingHint, percent, subjectLabel,
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

  const circled = circledQuestions(stats?.questions ?? [])
  const hintText = stats ? pendingHint(stats.pending_review) : null
  const hintMark = stats ? `${stats.pending_review} 项没复核` : ''
  const [hintBefore, hintAfter] = hintText?.split(hintMark) ?? []
  const hint = hintText && hintAfter !== undefined ? { before: hintBefore, mark: hintMark, after: hintAfter } : null
  const heading = assignment
    ? [className, subjectLabel(assignment.subject), assignment.title, dateText(assignment.created_at)]
        .filter(Boolean)
        .join(' · ')
    : ''

  return (
    <>
      <Header />
      <main id="main-content" className="page overview" tabIndex={-1}>
        <Link to="/" className="back">← 返回班级</Link>
        <div className="work-actions"><Link to={`/a/${assignmentId}/work`}>批改进度</Link><Link to={`/a/${assignmentId}/review`}>复核作答</Link><Link to={`/a/${assignmentId}/grades`}>学生成绩</Link><Link to={`/a/${assignmentId}/practice`}>巩固练习</Link></div>
        {error && <p className="err" role="alert">{error}</p>}
        {!error && !(assignment && stats) && <p className="empty">加载中…</p>}
        {assignment && stats && (
          <>
            <div className="page-heading overview-heading"><div><h1 className="main-title">{assignment.title}</h1><p>{[className, subjectLabel(assignment.subject), dateText(assignment.created_at)].filter(Boolean).join(' · ')}</p></div><Link className="dl-link" to={`/a/${assignmentId}/downloads`}><Icon name="print" size={18} />下载打印</Link></div>
            <div className="stat-row">
              <div className="stat"><span className="num">{stats.counted_students} / {stats.roster_size}</span><span className="lbl">已计入 / 全班人数</span></div>
              <div className="stat"><span className="num">{avgText(stats.average_score)}</span><span className="lbl">平均分</span></div>
              <div className="stat"><span className="num">{percent(stats.pass_rate)}</span><span className="lbl">及格率</span></div>
            </div>
            {hint && (
              // the one wavy underline on this screen
              <p className="pending-hint">{hint.before}<span className="red-wavy">{hint.mark}</span>{hint.after}</p>
            )}
            <div className="section-heading heat-heading"><div><h2 className="serif">每道题，错在哪里</h2><p>查看错误率，点击题目进入课堂讲评。</p></div><div className="heat-legend"><span><i className="legend-circle" />红圈：错得最多的题</span><span><i className="legend-hot" />≥ 40%</span><span><i className="legend-warm" />20–39%</span><span><i className="legend-cool" />低于 20%</span></div></div>
            {stats.questions.length === 0 ? (
              <p className="empty">还没有错题数据</p>
            ) : (
              <div className="q-grid">
                {stats.questions.map((q) => {
                  const rate = errorRate(q)
                  const heat = heatLevel(rate)
                  return (
                    <Link
                      key={q.question_no}
                      to={`/a/${assignmentId}/q/${encodeURIComponent(q.question_no)}`}
                      className={`q-cell heat-${heat}`}
                    >
                      <span className="qno serif">第 {q.question_no} 题</span>
                      <span className="qpct serif">{circled.has(q.question_no) ? <RedCircle>{percent(rate)}</RedCircle> : percent(rate)}</span>
                      <span className="q-count">{q.wrong_count} / {q.student_count} 人答错</span>
                      <span className="q-knowledge">{q.knowledge_point || '查看作答详情'}</span>
                      {q.is_subjective && <span className="qsub">主观</span>}
                    </Link>
                  )
                })}
              </div>
            )}
            <p className="workspace-footnote">统计会随复核结果更新。讲评页面不展示学生姓名。</p>
          </>
        )}
      </main>
    </>
  )
}
