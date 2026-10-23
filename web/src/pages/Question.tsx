import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Header from '../components/Header'
import Lightbox from '../components/Lightbox'
import { errorText, request } from '../lib/api'
import { percent, type Analytics } from '../lib/overview'
import { cropsByGroup, neighbors, type QuestionDetail } from '../lib/question'

const AI_LABEL = 'AI 推测'
const PREVIEW = 3

/** Projector page. It must never render a student name, anywhere (text, title, alt, data-*). */
export default function Question() {
  const { assignmentId, questionNo = '' } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<QuestionDetail | null>(null)
  const [order, setOrder] = useState<string[]>([])
  const [causes, setCauses] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [zoom, setZoom] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const base = `/api/assignments/${assignmentId}/analytics/questions/${encodeURIComponent(questionNo)}`

  useEffect(() => {
    let alive = true
    setError('')
    setDetail(null)
    setCauses({})
    setExpanded({})
    setZoom(null)
    request<QuestionDetail>('GET', base)
      .then((d) => {
        if (!alive) return
        setDetail(d)
        if (d.is_subjective) return
        // AI causes: asked once after the page is readable; failure is silent
        request<{ causes?: Record<string, string> }>('POST', `${base}/causes`)
          .then((r) => alive && setCauses(r.causes ?? {}))
          .catch(() => {})
      })
      .catch((e) => alive && setError(errorText(e)))
    return () => {
      alive = false
    }
  }, [base])

  useEffect(() => {
    let alive = true
    setOrder([])
    request<Analytics>('GET', `/api/assignments/${assignmentId}/analytics`)
      .then((a) => alive && setOrder(a.questions.map((q) => q.question_no)))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [assignmentId])

  const { prev, next } = neighbors(order, questionNo)
  const go = useCallback(
    (no: string | null) => {
      if (no !== null) navigate(`/a/${assignmentId}/q/${encodeURIComponent(no)}`)
    },
    [navigate, assignmentId],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (zoom) return
      if (e.key === 'ArrowLeft') go(prev)
      else if (e.key === 'ArrowRight') go(next)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, prev, next, zoom])

  const fullscreen = () => {
    void document.documentElement.requestFullscreen?.()?.catch?.(() => {})
  }
  const closeZoom = useCallback(() => setZoom(null), [])

  const rate = detail && detail.student_count > 0 ? detail.wrong_count / detail.student_count : null
  const crops = detail ? cropsByGroup(detail.groups, detail.crops ?? []) : new Map<string, string[]>()

  return (
    <>
      <Header />
      <main className="page question">
        <div className="q-toolbar">
          <Link to={`/a/${assignmentId}`} className="back">← 返回总览</Link>
          <span className="q-spacer" />
          <button type="button" disabled={prev === null} onClick={() => go(prev)}>上一题</button>
          <button type="button" disabled={next === null} onClick={() => go(next)}>下一题</button>
          <button type="button" onClick={fullscreen}>全屏</button>
        </div>
        {error && <p className="err">{error}</p>}
        {!error && !detail && <p className="empty">加载中…</p>}
        {detail && (
          <>
            <h1 className="main-title q-headline">
              第 {detail.question_no} 题　错了 {detail.wrong_count} 人（{percent(rate)}）
            </h1>
            <div className="q-bar" aria-hidden="true">
              <div className="q-bar-fill" style={{ width: `${Math.round((rate ?? 0) * 100)}%` }} />
            </div>
            <p className="q-meta">
              正确答案：{detail.correct_answer ?? '（无）'}
              {detail.knowledge_point ? `　知识点：${detail.knowledge_point}` : ''}
            </p>

            {detail.is_subjective ? (
              <>
                <div className="q-buckets">
                  {detail.score_buckets.map((b) => (
                    <div className="q-bucket" key={b.label}>
                      <span>{b.label}</span>
                      <strong>{b.count} 人</strong>
                    </div>
                  ))}
                </div>
                <div className="q-crops">
                  {(detail.crops ?? []).map((c, i) => (
                    <img key={`${c.submission_id}-${i}`} src={c.crop_url} alt="学生作答原图" onClick={() => setZoom(c.crop_url)} />
                  ))}
                </div>
              </>
            ) : detail.groups.length === 0 ? (
              <p className="empty">这道题没有人答错</p>
            ) : (
              detail.groups.map((g) => {
                const urls = crops.get(g.key) ?? []
                const open = expanded[g.key]
                const shown = open ? urls : urls.slice(0, PREVIEW)
                const more = urls.length - PREVIEW
                return (
                  <section className="q-group" key={g.key}>
                    <h2>写成 {g.answer || '（空白）'}，{g.count} 人</h2>
                    <div className={open ? 'q-crops open' : 'q-crops'}>
                      {shown.map((u) => (
                        <img key={u} src={u} alt="学生作答原图" onClick={() => setZoom(u)} />
                      ))}
                      {!open && more > 0 && (
                        <button type="button" className="q-more" onClick={() => setExpanded({ ...expanded, [g.key]: true })}>
                          还有 {more} 张
                        </button>
                      )}
                    </div>
                    <p className="q-cause">
                      {causes[g.key] && (
                        <>
                          {causes[g.key]}
                          <span className="q-ai">{AI_LABEL}</span>
                        </>
                      )}
                    </p>
                  </section>
                )
              })
            )}
          </>
        )}
      </main>
      {zoom && <Lightbox src={zoom} onClose={closeZoom} />}
    </>
  )
}
