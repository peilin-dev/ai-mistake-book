import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import PageThumbnail from '../components/PageThumbnail'
import { errorText, request } from '../lib/api'
import {
  ACCEPT,
  expandFiles,
  MAX_BATCH,
  type BadFile,
  type SourcePage,
} from '../lib/intake'
import { summaryText, uploadAll, type UploadState } from '../lib/uploader'
import { useLeaveGuard } from '../lib/useLeaveGuard'
import { takeAssignmentMaterials } from '../lib/assignmentMaterials'
type State = { state: UploadState; error?: string }
const labels: Record<UploadState, string> = {
  waiting: '等待上传',
  uploading: '正在上传',
  done: '上传成功',
  duplicate: '已经传过，跳过',
  failed: '上传失败',
  skipped_quota: '额度不足，未上传',
}
export default function Upload() {
  const { assignmentId } = useParams()
  const navigate = useNavigate()
  const [pages, setPages] = useState<SourcePage[]>([]),
    [bad, setBad] = useState<BadFile[]>([]),
    [states, setStates] = useState<Record<string, State>>({}),
    [remaining, setRemaining] = useState<number | null>(null),
    [busy, setBusy] = useState(false),
    [expanding, setExpanding] = useState(false),
    [error, setError] = useState(''),
    [summary, setSummary] = useState('')
  const lock = useRef(false),
    drag = useRef<string>(),
    live = useRef(true),
    controller = useRef<AbortController>()
  useEffect(() => {
    live.current = true
    return () => {
      live.current = false
      controller.current?.abort()
    }
  }, [])
  async function quota() {
    try {
      const me = await request<{ quota_total: number; quota_used: number }>(
        'GET',
        '/api/me',
      )
      if (live.current)
        setRemaining(Math.max(0, me.quota_total - me.quota_used))
    } catch (e) {
      if (live.current) setError(errorText(e))
    }
  }
  useEffect(() => {
    void quota()
  }, [])
  const pending = pages.filter(
    (p) => !['done', 'duplicate'].includes(states[p.id]?.state),
  ).length
  useLeaveGuard(busy, `还有 ${pending} 页没传完，确定离开吗？`)
  async function add(files: File[]) {
    if (lock.current || !files.length) return
    lock.current = true
    setExpanding(true)
    setError('')
    setSummary('')
    try {
      const result = await expandFiles(files)
      if (live.current) {
        setPages((old) => [...old, ...result.pages])
        setBad((old) => [...old, ...result.bad])
      }
    } catch (e) {
      if (live.current) setError(errorText(e))
    } finally {
      lock.current = false
      if (live.current) setExpanding(false)
    }
  }
  useEffect(() => {
    const timer = setTimeout(() => {
      const files = takeAssignmentMaterials(Number(assignmentId))
      if (files.length) void add(files)
    }, 0)
    return () => clearTimeout(timer)
  }, [assignmentId])
  async function upload(list: SourcePage[]) {
    if (
      lock.current ||
      !list.length ||
      pages.length > MAX_BATCH ||
      remaining === null
    )
      return
    lock.current = true
    controller.current = new AbortController()
    setBusy(true)
    setError('')
    setSummary('')
    try {
      const result = await uploadAll(
        Number(assignmentId),
        list,
        (id, state, err) => {
          if (live.current)
            setStates((old) => ({ ...old, [id]: { state, error: err } }))
        },
        3,
        controller.current.signal,
      )
      if (live.current) {
        setSummary(summaryText(result))
        await quota()
      }
    } catch (e) {
      if (live.current) setError(errorText(e))
    } finally {
      lock.current = false
      if (live.current) setBusy(false)
    }
  }
  function move(id: string, delta: number) {
    setPages((old) => {
      const next = [...old],
        i = next.findIndex((p) => p.id === id),
        j = i + delta
      if (j >= 0 && j < next.length) [next[i], next[j]] = [next[j], next[i]]
      return next
    })
  }
  const ready = pages.filter(
      (p) => !['done', 'duplicate'].includes(states[p.id]?.state),
    ),
    over = pages.length > MAX_BATCH
  const complete = Boolean(summary) && !busy && !expanding && bad.length === 0 &&
    pages.length > 0 && pages.every(p => ['done', 'duplicate'].includes(states[p.id]?.state))
  useEffect(() => {
    if (!complete) return
    // Let the completed upload release the route-leave guard before navigating.
    const timer = setTimeout(() => navigate(`/a/${assignmentId}/work`, {
      replace: true,
      state: { uploadSummary: summary },
    }), 0)
    return () => clearTimeout(timer)
  }, [complete, navigate, assignmentId, summary])
  return (
    <WorkShell
      title="上传学生卷子"
      description="支持照片、PDF 和 ZIP。照片按拍摄时间排列，读不到时间时按文件名排列。"
    >
      <section
        className="upload-drop"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          void add(Array.from(e.dataTransfer.files))
        }}
      >
        <h2 className="serif">把卷子拖到这里</h2>
        <p>JPG / PNG / WebP / HEIC · PDF 每页一张 · ZIP 自动展开</p>
        <label className="file-button btn-primary">
          {expanding ? '正在整理文件…' : '选择文件'}
          <input
            type="file"
            multiple
            accept={ACCEPT}
            disabled={busy || expanding}
            onChange={(e) => {
              void add(Array.from(e.target.files ?? []))
              e.target.value = ''
            }}
          />
        </label>
        <p>一次最多上传 200 页；全部上传成功后自动进入批改进度。</p>
      </section>
      {error && (
        <p className="err" role="alert">
          {error}
        </p>
      )}
      {bad.length > 0 && (
        <section className="notice">
          <h2>这些文件没能加入</h2>
          <ul>
            {bad.map((b, i) => (
              <li key={i}>
                {b.fileName}：{b.reason}
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="section-heading">
        <h2 className="serif">本批共 {pages.length} 页</h2>
        <p>
          {remaining === null
            ? '正在读取额度…'
            : `本月还能批改 ${remaining} 页`}
        </p>
      </div>
      {over && (
        <p role="alert" className="err">
          一次最多上传 200 页，请分批上传。当前列表保留前 201
          页用于提示，请删除多余页，并把其余文件另分一批。
        </p>
      )}
      {!over && remaining !== null && ready.length > remaining && (
        <p className="notice">
          本月还能批改 {remaining} 页，这批有 {ready.length} 页。
          <button
            disabled={busy || expanding || remaining === 0}
            onClick={() => void upload(ready.slice(0, remaining))}
          >
            只传前 {remaining} 页
          </button>
        </p>
      )}
      <div className="upload-grid">
        {pages.map((page, i) => (
          <article
            className="upload-page"
            key={page.id}
            draggable={!busy && !expanding}
            onDragStart={(e) => {
              drag.current = page.id
              e.dataTransfer.setData('text/plain', page.id)
            }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              e.stopPropagation()
              if (busy || expanding || !drag.current) return
              const from = pages.findIndex((p) => p.id === drag.current)
              move(drag.current, i - from)
              drag.current = undefined
            }}
          >
            <PageThumbnail page={page} />
            <h3>{page.fileName}</h3>
            <p>{page.pageNo ? `PDF 第 ${page.pageNo} 页` : `第 ${i + 1} 张`}</p>
            <p aria-live="polite">
              {states[page.id] ? labels[states[page.id].state] : '等待上传'}
            </p>
            {states[page.id]?.error && (
              <p className="err">{states[page.id].error}</p>
            )}
            <div className="row-buttons">
              <button
                disabled={busy || expanding || i === 0}
                onClick={() => move(page.id, -1)}
                aria-label={`上移 ${page.fileName}`}
              >
                上移
              </button>
              <button
                disabled={busy || expanding || i === pages.length - 1}
                onClick={() => move(page.id, 1)}
                aria-label={`下移 ${page.fileName}`}
              >
                下移
              </button>
              <button
                disabled={busy || expanding}
                onClick={() =>
                  setPages((old) => old.filter((p) => p.id !== page.id))
                }
              >
                移出
              </button>
              {states[page.id]?.state === 'failed' && (
                <button disabled={busy} onClick={() => void upload([page])}>
                  重试
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
      <div className="work-actions">
        <button
          className="btn-primary"
          disabled={
            busy ||
            expanding ||
            !ready.length ||
            over ||
            remaining === null ||
            ready.length > remaining
          }
          onClick={() => void upload(ready)}
        >
          {busy ? '正在上传…' : '开始上传'}
        </button>
        <Link to={`/a/${assignmentId}/work`}>去作业页</Link>
      </div>
      {busy && (
        <p role="status">
          已处理{' '}
          {
            pages.filter((p) =>
              ['done', 'duplicate', 'failed', 'skipped_quota'].includes(
                states[p.id]?.state,
              ),
            ).length
          }{' '}
          / {pages.length} 页，请保持此页面打开。
        </p>
      )}
      {summary && (
        <p role="status" className="notice">
          {summary}
        </p>
      )}
    </WorkShell>
  )
}
