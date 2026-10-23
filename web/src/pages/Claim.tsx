import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import Confirm from '../components/Confirm'
import { request, errorText } from '../lib/api'
interface Candidate {
  student_id: number
  name: string
  missing_all: boolean
  page_count: number
  thumb_url: string | null
}
interface ClaimInfo {
  page_id: number
  image_url: string | null
  question_nos: string[]
  candidates: Candidate[]
}
export default function Claim() {
  const { assignmentId } = useParams()
  const [list, setList] = useState<number[] | null>(null),
    [info, setInfo] = useState<ClaimInfo>(),
    [selected, setSelected] = useState(0),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [discard, setDiscard] = useState(false),
    [reload, setReload] = useState(0)
  const lock = useRef(false)
  useEffect(() => {
    let live = true
    request<{ pages_unassigned: { page_id: number }[] }>(
      'GET',
      `/api/assignments/${assignmentId}/review`,
    )
      .then((r) => live && setList(r.pages_unassigned.map((p) => p.page_id)))
      .catch((e) => live && setError(errorText(e)))
    return () => {
      live = false
    }
  }, [assignmentId, reload])
  const current = list?.[0]
  useEffect(() => {
    let live = true
    setInfo(undefined)
    setSelected(0)
    if (current)
      request<ClaimInfo>('GET', `/api/pages/${current}/claim-candidates`)
        .then((r) => {
          if (live) {
            setInfo(r)
            setError('')
          }
        })
        .catch((e) => live && setError(errorText(e)))
    return () => {
      live = false
    }
  }, [current, reload])
  const process = useCallback(
    async (remove = false) => {
      if (lock.current || !info || (!remove && !info.candidates[selected]))
        return
      lock.current = true
      setBusy(true)
      setError('')
      try {
        await request(
          remove ? 'DELETE' : 'PATCH',
          `/api/pages/${info.page_id}`,
          remove
            ? undefined
            : { student_id: info.candidates[selected].student_id },
        )
        setList((old) => old?.filter((id) => id !== info.page_id) ?? [])
        setDiscard(false)
      } catch (e) {
        setError(errorText(e))
      } finally {
        lock.current = false
        setBusy(false)
      }
    },
    [info, selected],
  )
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (
        busy ||
        discard ||
        !info ||
        (e.target instanceof Element &&
          e.target.closest(
            'input,textarea,select,button,a,[contenteditable=true]',
          ))
      )
        return
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelected((i) => Math.min(i + 1, info.candidates.length - 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelected((i) => Math.max(0, i - 1))
      }
      if (e.key === 'Enter') {
        e.preventDefault()
        void process()
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [info, busy, discard, process])
  return (
    <WorkShell
      title="待认领卷子"
      description="候选仅按缺少的题号排序，请核对原图后确认学生。上下键选择，回车确认。"
    >
      {error && (
        <p role="alert" className="err">
          {error}
          <button onClick={() => setReload((n) => n + 1)}>重新加载</button>
        </p>
      )}
      {list?.length === 0 ? (
        <p className="empty">没有待认领的页了</p>
      ) : !info ? (
        !error && <p className="empty">加载中…</p>
      ) : (
        <>
          <p>
            还有 {list?.length} 页 · 本页题号：
            {info.question_nos.join('、') || '未识别题号'}
          </p>
          <div className="claim-layout">
            <div className="source-image">
              {info.image_url ? (
                <a href={info.image_url} target="_blank" rel="noreferrer">
                  <img src={info.image_url} alt="待认领试卷，点击查看原图" />
                </a>
              ) : (
                <p className="empty">原图已过保存期，请结合题号核对</p>
              )}
            </div>
            <section aria-label="候选学生">
              <h2 className="serif">这张卷子是谁的？</h2>
              <div className="candidate-list">
                {info.candidates.map((c, i) => (
                  <button
                    key={c.student_id}
                    aria-pressed={selected === i}
                    disabled={busy}
                    onClick={() => setSelected(i)}
                  >
                    <span>
                      <strong>{c.name}</strong>
                      <small>
                        {c.missing_all ? '缺这些题' : '已有部分同题号'} · 已有{' '}
                        {c.page_count} 页
                      </small>
                    </span>
                    {c.thumb_url && (
                      <img src={c.thumb_url} alt={`${c.name} 已有卷子缩略图`} />
                    )}
                  </button>
                ))}
              </div>
              {info.candidates.length === 0 && (
                <p>班级还没有学生，请先在班级管理中添加名单。</p>
              )}
              <div className="work-actions">
                <button
                  className="btn-primary"
                  disabled={busy || !info.candidates.length}
                  onClick={() => void process()}
                >
                  {busy ? '正在处理…' : '确认归属'}
                </button>
                <button disabled={busy} onClick={() => setDiscard(true)}>
                  废页 / 不是这个班的
                </button>
              </div>
            </section>
          </div>
        </>
      )}
      {discard && (
        <Confirm
          title="删除这张卷子？"
          message="图片和批改结果会一起删除，无法恢复，也不退还批改额度。"
          confirmText="删除废页"
          danger
          onCancel={() => setDiscard(false)}
          onConfirm={() => {
            setDiscard(false)
            void process(true)
          }}
        />
      )}
    </WorkShell>
  )
}
