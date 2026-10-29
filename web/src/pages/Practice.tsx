import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import Confirm from '../components/Confirm'
import { ApiError, request, errorText } from '../lib/api'
interface Item {
  id: number
  position: number
  source_no: string
  knowledge_point: string | null
  stem: string
  options: string[] | null
  answer: string
  replacing: boolean
}
interface Paper {
  id: number
  status: string
  partial: boolean
  sources_total: number
  sources_done: number
  error: string | null
  last_replace_failed_item: number | null
  items: Item[]
  student_name: string | null
}
export default function Practice() {
  const { assignmentId, submissionId } = useParams()
  return <PracticeEditor key={`${assignmentId}:${submissionId || "class"}`} />
}
function PracticeEditor() {
  const { assignmentId, submissionId } = useParams()
  const path = submissionId
    ? `/api/submissions/${submissionId}/practice`
    : `/api/assignments/${assignmentId}/practice`
  const [paper, setPaper] = useState<Paper | null>(),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [reload, setReload] = useState(0),
    [regenerate, setRegenerate] = useState(false),
    [answers, setAnswers] = useState(false)
  const lock = useRef(false)
  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout>
    const load = async () => {
      try {
        const r = await request<Paper>('GET', path)
        if (!live) return
        setPaper(r)
        if (
          ['queued', 'running'].includes(r.status) ||
          r.items.some((i) => i.replacing)
        )
          timer = setTimeout(load, 3000)
      } catch (e) {
        if (!live) return
        if (e instanceof ApiError && e.status === 404) setPaper(null)
        else setError(errorText(e))
      }
    }
    void load()
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [path, reload])
  const working =
    !!paper &&
    (['queued', 'running'].includes(paper.status) ||
      paper.items.some((i) => i.replacing))
  async function generate() {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setError('')
    setRegenerate(false)
    try {
      const r = await request<Paper>('POST', path)
      setPaper(r)
      setReload((n) => n + 1)
    } catch (e) {
      setError(errorText(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  return (
    <WorkShell
      title={
        submissionId
          ? `${paper?.student_name || '学生'}的练习卷`
          : '全班巩固练习'
      }
      description="根据已归属、已批改的错题生成练习，生成后请核对题目与答案。"
    >
      {error && (
        <p role="alert" className="err">
          {error}
        </p>
      )}
      {paper === undefined && !error && <p className="empty">加载中…</p>}
      {paper === null && (
        <p className="empty">
          还没有练习卷。点击生成，按错题准备一份巩固练习。
        </p>
      )}
      <div className="work-actions">
        <button
          className="btn-primary"
          disabled={busy || working || paper === undefined}
          onClick={() =>
            paper?.items.length ? setRegenerate(true) : void generate()
          }
        >
          {working
            ? '正在出题…'
            : paper?.items.length
              ? '重新生成练习卷'
              : '生成练习卷'}
        </button>
        <label>
          <input
            type="checkbox"
            checked={answers}
            onChange={(e) => setAnswers(e.target.checked)}
          />
          显示参考答案
        </label>
        <Link
          to={
            submissionId
              ? `/a/${assignmentId}/students/${submissionId}`
              : `/a/${assignmentId}/downloads`
          }
        >
          {submissionId ? '返回个人详情打印' : '下载与打印'}
        </Link>
      </div>
      {working && (
        <p role="status" className="notice">
          正在出题… 已处理 {paper?.sources_done} / {paper?.sources_total} 组错题
        </p>
      )}
      {paper?.status === 'failed' && (
        <p role="alert" className="err">
          这张练习纸没出成，请重新生成。
        </p>
      )}
      {paper?.partial && (
        <p className="notice">
          部分题没能生成，已保留可用题目。可以重新生成补齐。
        </p>
      )}
      {paper?.last_replace_failed_item && (
        <p role="status" className="notice">
          有一道题没换成，原题已保留，可以再试。
        </p>
      )}
      {paper?.items.map((item) => (
        <section key={item.id} className="question-row">
          <div className="section-heading">
            <h2 className="serif">第 {item.position} 题</h2>
            <button
              disabled={busy || working}
              onClick={async () => {
                if (lock.current) return
                lock.current = true
                setBusy(true)
                setError('')
                try {
                  await request(
                    'POST',
                    `/api/practice-items/${item.id}/replace`,
                  )
                  setReload((n) => n + 1)
                } catch (e) {
                  setError(errorText(e))
                } finally {
                  lock.current = false
                  setBusy(false)
                }
              }}
            >
              {item.replacing ? '正在换题…' : '换一道'}
            </button>
          </div>
          <p className="hint">
            来源：第 {item.source_no} 题
            {item.knowledge_point ? ` · ${item.knowledge_point}` : ''}
          </p>
          <p className="preserve-lines">{item.stem}</p>
          {item.options?.map((option, i) => (
            <p key={i}>{option}</p>
          ))}
          {answers && <p className="notice">参考答案：{item.answer}</p>}
        </section>
      ))}
      {regenerate && (
        <Confirm
          title="重新生成练习卷？"
          message="新的练习卷会替换当前题目，生成后请重新核对。"
          confirmText="重新生成"
          onCancel={() => setRegenerate(false)}
          onConfirm={() => void generate()}
        />
      )}
    </WorkShell>
  )
}
