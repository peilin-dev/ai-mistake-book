import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import Confirm from '../components/Confirm'
import WorkflowSteps from '../components/WorkflowSteps'
import { request, errorText } from '../lib/api'
import {
  canRetry,
  pageStatusText,
  type PageItem,
  type Progress,
} from '../lib/pages'
import { imageBody, prepareOne } from '../lib/intake'
export default function AssignmentWork() {
  const { assignmentId } = useParams()
  const location = useLocation()
  const uploadSummary = typeof location.state?.uploadSummary === 'string'
    ? location.state.uploadSummary : ''
  const [title, setTitle] = useState('作业批改'),
    [pages, setPages] = useState<PageItem[] | null>(null),
    [progress, setProgress] = useState<Progress>(),
    [updated, setUpdated] = useState(''),
    [error, setError] = useState(''),
    [deleting, setDeleting] = useState<PageItem>(),
    [busy, setBusy] = useState(false),
    [reload, setReload] = useState(0)
  const lock = useRef(false)
  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout>
    const load = async () => {
      try {
        const [a, p, list] = await Promise.all([
          request<{ title: string }>('GET', `/api/assignments/${assignmentId}`),
          request<Progress>('GET', `/api/assignments/${assignmentId}/progress`),
          request<PageItem[]>('GET', `/api/assignments/${assignmentId}/pages`),
        ])
        if (!live) return
        setTitle(a.title)
        setProgress(p)
        setPages(list)
        setError('')
        setUpdated(new Date().toLocaleTimeString())
        if (p.queued + p.processing > 0) timer = setTimeout(load, 3000)
      } catch (e) {
        if (live) { setError(errorText(e)); timer = setTimeout(load, 5000) }
      }
    }
    void load()
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [assignmentId, reload])
  async function act(fn: () => Promise<unknown>) {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setError('')
    try {
      await fn()
      setReload((n) => n + 1)
    } catch (e) {
      setError(errorText(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  const unclaimed =
    pages?.filter((p) => p.status === 'done' && p.student_id === null).length ??
    0
  const percentage = progress?.total ? Math.floor(progress.done / progress.total * 100) : 0
  return (
    <WorkShell
      title={title}
      description="先核对答案，再上传卷子；批改后处理待认领与复核。"
    >
      {uploadSummary && <p className="notice" role="status">{uploadSummary}。上传已完成，可在下方查看批改进度。</p>}
      {progress && <WorkflowSteps assignmentId={assignmentId!} current={!progress.total ? 0 : progress.queued + progress.processing || progress.failed ? 1 : unclaimed || progress.needs_review ? 2 : 3} unclaimed={unclaimed} />}
      {error && (
        <p className="err" role="alert">
          {error}
          <button onClick={() => setReload((n) => n + 1)}>重新加载</button>
        </p>
      )}
      <div className="work-actions">
        <Link className="btn-primary" to={`/a/${assignmentId}/upload`}>
          上传卷子
        </Link>
        <Link to={`/a/${assignmentId}/answer-key`}>上传或核对答案卷</Link>
        <Link to={`/a/${assignmentId}/claim`}>待认领 {unclaimed} 页</Link>
      </div>
      {progress && (
        <section className="progress-strip" aria-label="批改进度">
          <div className="section-heading"><h2>{progress.queued + progress.processing > 0 ? '正在批改' : progress.total ? '本批处理结束' : '等待上传'}</h2><button onClick={() => setReload(n => n + 1)}>刷新进度</button></div>
          <p className="hint" role="status">{progress.queued + progress.processing > 0 ? '每 3 秒自动更新，无需手动刷新。' : '上传新卷后继续更新。'}{updated && ` 最近更新 ${updated}`}</p>
          <div className="grading-progress-numbers" aria-live="polite" aria-atomic="true"><p>
            <strong>
              {progress.done} / {progress.total}
            </strong>{' '}
            页已完成
          </p><strong className="grading-percentage">{percentage}%</strong></div>
          <progress aria-label="已成功批改比例" aria-valuetext={`已成功批改 ${progress.done} / ${progress.total} 页，${percentage}%`} value={progress.done} max={Math.max(progress.total, 1)} />
          <p>
            排队 {progress.queued} · 批改中 {progress.processing} · 失败{' '}
            {progress.failed} · 需复核 {progress.needs_review}
          </p>
          {progress.done > 0 && <div className="work-actions">
            {unclaimed > 0 && <Link className="btn-primary" to={`/a/${assignmentId}/claim`}>先认领 {unclaimed} 页</Link>}
            {progress.needs_review > 0 && <Link className={unclaimed ? '' : 'btn-primary'} to={`/a/${assignmentId}/review`}>复核 {progress.needs_review} 题</Link>}
            <Link className={!unclaimed && !progress.needs_review ? 'btn-primary' : ''} to={`/a/${assignmentId}/grades`}>查看成绩与原卷</Link>
          </div>}
        </section>
      )}
      {pages === null && !error && <p className="empty">加载中…</p>}
      {pages?.length === 0 && (
        <p className="empty">还没有卷子。先核对答案卷，再上传学生试卷。</p>
      )}
      {!!pages?.length && (
        <div className="table-scroll">
          <table className="work-table">
            <thead>
              <tr>
                <th>页序</th>
                <th>来源</th>
                <th>学生</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {pages.map((p) => (
                <tr key={p.page_id}>
                  <td>第 {p.seq} 页</td>
                  <td>{p.source === 'web' ? '网页' : '手机'}</td>
                  <td>{p.student_name || p.recognized_name || '未识别姓名'}</td>
                  <td>{pageStatusText(p)}</td>
                  <td className="row-buttons">
                    {canRetry(p) && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          void act(() =>
                            request('POST', `/api/pages/${p.page_id}:retry`),
                          )
                        }
                      >
                        重试
                      </button>
                    )}
                    {p.status === 'failed' && (
                      <label className="file-button">
                        换一张
                        <input
                          type="file"
                          accept=".jpg,.jpeg,.png,.heic,.heif,.webp"
                          disabled={busy}
                          onChange={(e) => {
                            const f = e.target.files?.[0]
                            e.target.value = ''
                            if (f)
                              void act(async () =>
                                request(
                                  'POST',
                                  `/api/pages/${p.page_id}:replace`,
                                  imageBody(await prepareOne(f)),
                                ),
                              )
                          }}
                        />
                      </label>
                    )}
                    <button disabled={busy} onClick={() => setDeleting(p)}>
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {deleting && (
        <Confirm
          title={`删除第 ${deleting.seq} 页？`}
          message="这页的图片和批改结果会一起删除，无法恢复，也不退还批改额度。"
          confirmText="删除这一页"
          danger
          onCancel={() => setDeleting(undefined)}
          onConfirm={() => {
            const id = deleting.page_id
            setDeleting(undefined)
            void act(() => request('DELETE', `/api/pages/${id}`))
          }}
        />
      )}
    </WorkShell>
  )
}
