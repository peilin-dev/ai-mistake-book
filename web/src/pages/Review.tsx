import GradingFeedback from '../components/GradingFeedback'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import ResultEditor from '../components/ResultEditor'
import StudentAssignment from '../components/StudentAssignment'
import { errorText, request } from '../lib/api'
import { reviewReason, type QuestionResult } from '../lib/results'
export default function Review() {
  const { assignmentId } = useParams()
  const [questions, setQuestions] = useState<QuestionResult[] | null>(null),
    [unassigned, setUnassigned] = useState(0),
    [index, setIndex] = useState(0),
    [error, setError] = useState(''),
    [reload, setReload] = useState(0)
  useEffect(() => {
    let live = true
    setQuestions(null)
    setIndex(0)
    request<{ questions: QuestionResult[]; pages_unassigned: unknown[] }>(
      'GET',
      `/api/assignments/${assignmentId}/review`,
    )
      .then((r) => {
        if (live) {
          setQuestions(r.questions)
          setUnassigned(r.pages_unassigned.length)
          setError('')
        }
      })
      .catch((e) => live && setError(errorText(e)))
    return () => {
      live = false
    }
  }, [assignmentId, reload])
  const current = questions?.[index]
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (
        e.target instanceof Element &&
        e.target.closest(
          'input,textarea,select,button,a,[contenteditable=true]',
        )
      )
        return
      if (e.key === 'ArrowRight') {
        e.preventDefault()
        setIndex((i) => Math.min(i + 1, (questions?.length ?? 1) - 1))
      }
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        setIndex((i) => Math.max(0, i - 1))
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [questions])
  return (
    <WorkShell
      title="批改复核"
      description="核对识别不确定或答案有分歧的题。修改后成绩与学情同步更新。"
    >
      {unassigned > 0 && (
        <p className="notice">
          还有 {unassigned} 页没有学生归属，建议先
          <Link to={`/a/${assignmentId}/claim`}>处理待认领</Link>。
        </p>
      )}
      {error && (
        <p className="err" role="alert">
          {error}
          <button onClick={() => setReload((n) => n + 1)}>重新加载</button>
        </p>
      )}
      {questions === null && !error && <p className="empty">加载中…</p>}
      {questions?.length === 0 && (
        <p className="empty">当前没有需要复核的题目了</p>
      )}
      {current && (
        <>
          <div className="section-heading">
            <p>
              剩余 {questions?.length} 项 · 当前第 {index + 1} 项
            </p>
            <div className="row-buttons">
              <button
                disabled={index === 0}
                onClick={() => setIndex((i) => i - 1)}
              >
                上一项
              </button>
              <button
                disabled={index >= (questions?.length ?? 0) - 1}
                onClick={() => setIndex((i) => i + 1)}
              >
                下一项
              </button>
            </div>
          </div>
          <div className="claim-layout">
            <div className="source-image">
              {current.crop_url || current.image_url ? (
                <a
                  href={(current.crop_url || current.image_url)!}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    src={(current.crop_url || current.image_url)!}
                    alt="题目作答原图，点击放大"
                  />
                </a>
              ) : (
                <p className="empty">没有可用原图</p>
              )}
            </div>
            <section className="review-copy">
              <StudentAssignment key={current.page_id} assignmentId={assignmentId!} pageId={current.page_id} onSaved={() => setReload(n => n+1)} />
              <h2 className="serif">
                {current.student_name || '未认领学生'} · 第{' '}
                {current.question_no} 题
              </h2>
              <p className="notice">{reviewReason(current.reason)}</p>
              <p>{current.question_text}</p>
              <dl>
                <dt>学生答案</dt>
                <dd>{current.student_answer || '未识别'}</dd>
                <dt>参考答案</dt>
                <dd>{current.correct_answer || '未识别'}</dd>
                <dt>当前判定</dt>
                <dd>
                  {current.is_subjective ? '评分' : current.is_correct ? '对' : '错'} · {current.score} /{' '}
                  {current.max_score ?? '未标分值'}
                </dd>
              </dl>
              <GradingFeedback question={current} />
              <ResultEditor
                key={current.id}
                question={current}
                onSaved={() => {
                  setQuestions(
                    (old) => old?.filter((q) => q.id !== current.id) ?? [],
                  )
                  setIndex((i) =>
                    Math.min(i, Math.max(0, (questions?.length ?? 1) - 2)),
                  )
                }}
              />
              <p className="hint">
                左右键切换；按 Tab 移到操作按钮后，可按回车确认。
              </p>
            </section>
          </div>
        </>
      )}
    </WorkShell>
  )
}
