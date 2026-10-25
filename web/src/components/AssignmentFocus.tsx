import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { errorText, request } from '../lib/api'
import type { AssignmentOut } from '../lib/overview'
import type { Progress, PageItem } from '../lib/pages'
import Icon from './Icon'
import WorkflowSteps from './WorkflowSteps'

export default function AssignmentFocus({ assignment }: { assignment: AssignmentOut }) {
  const [data, setData] = useState<{ id: number; progress: Progress; unclaimed: number }>()
  const [error, setError] = useState(''), [reload, setReload] = useState(0)
  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout>
    const controller = new AbortController()
    setError('')
    async function load() {
      try {
        const [progress, pages] = await Promise.all([
          request<Progress>('GET', `/api/assignments/${assignment.id}/progress`, undefined, controller.signal),
          request<PageItem[]>('GET', `/api/assignments/${assignment.id}/pages`, undefined, controller.signal),
        ])
        if (!live) return
        if (!Number.isFinite(progress.total) || !Array.isArray(pages)) throw new Error('暂时无法读取作业状态')
        setData({ id: assignment.id, progress, unclaimed: pages.filter(p => p.status === 'done' && p.student_id === null).length })
        setError('')
        if (progress.queued + progress.processing > 0) timer = setTimeout(load, 3000)
      } catch (e) { if (live) setError(errorText(e)) }
    }
    void load()
    return () => { live = false; clearTimeout(timer); controller.abort() }
  }, [assignment.id, reload])
  const fresh = data?.id === assignment.id ? data : undefined
  const p = error ? undefined : fresh?.progress
  const pending = p ? p.queued + p.processing : 0
  const current = !p ? -1 : !p.total ? 0 : pending || p.failed ? 1 : fresh!.unclaimed || p.needs_review ? 2 : 3
  const label = !p ? '正在读取状态' : !p.total ? '等待上传' : pending ? '正在批改' : p.failed ? '有失败页待处理' : fresh!.unclaimed || p.needs_review ? '等待老师确认' : '可查看成绩'
  return <section className="assignment-focus" aria-label="最近作业处理区">
    <div className="focus-overview"><div><div className="focus-heading"><h2>继续处理</h2><span className={`activity-badge ${pending ? 'is-running' : p?.failed || p?.needs_review || fresh?.unclaimed ? 'is-attention' : p?.total ? 'is-ready' : ''}`}><i aria-hidden="true" />{error ? '状态暂不可用' : label}</span></div><Link className="focus-assignment-title" to={`/a/${assignment.id}/work`}>{assignment.title}<Icon name="arrow" size={17} /></Link><p>本班最近创建的作业 · 以下状态仅对应这份作业</p></div>
      <div className="focus-progress" aria-live="polite">{p && !error ? <><span>已批改 {p.done} / {p.total} 页</span><strong>{p.total ? Math.floor(p.done / p.total * 100) : 0}%</strong><progress aria-label="最近作业批改进度" value={p.done} max={Math.max(1, p.total)} /></> : <span>{error || '正在获取实际批改进度…'}</span>}</div>
    </div>
    <WorkflowSteps assignmentId={assignment.id} current={current} unclaimed={fresh?.unclaimed} />
    <div className="focus-actions">
      <Link to={`/a/${assignment.id}/upload`}><Icon name="upload" size={17} />继续上传</Link>
      {!error && !!fresh?.unclaimed && <Link className="attention-link" to={`/a/${assignment.id}/claim`}>认领 {fresh.unclaimed} 页</Link>}
      {!!p?.needs_review && <Link className="attention-link" to={`/a/${assignment.id}/review`}>复核 {p.needs_review} 题</Link>}
      {!!p?.failed && <Link className="attention-link" to={`/a/${assignment.id}/work`}>处理失败 {p.failed} 页</Link>}
      {!!p?.done && <Link to={`/a/${assignment.id}/grades`}>查看原卷与成绩<Icon name="arrow" size={15} /></Link>}
      <button type="button" onClick={() => setReload(n => n + 1)}>{error ? '重试读取状态' : '刷新状态'}</button>
    </div>
  </section>
}
