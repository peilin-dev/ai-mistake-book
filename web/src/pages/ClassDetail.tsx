import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import Confirm from '../components/Confirm'
import Header from '../components/Header'
import RosterField from '../components/RosterField'
import { ApiError, errorText, request } from '../lib/api'
import { importNotice, type ClassOut, type ImportOut, type StudentOut } from '../lib/classes'
import { previewRoster } from '../lib/roster'

type Load = 'loading' | 'ok' | 'notfound' | 'error'

function StudentRow({ s, onEdit, onRemove, busy }: {
  s: StudentOut
  onEdit: (s: StudentOut) => void
  onRemove: (s: StudentOut) => void
  busy: boolean
}) {
  return (
    <li className="student-row">
      <span className="student-name">{s.name}</span>
      <span className="student-no">{s.student_no ? `学号 ${s.student_no}` : '未填学号'}</span>
      <span className="student-actions">
        <button type="button" aria-label={`修改 ${s.name}`} disabled={busy} onClick={() => onEdit(s)}>修改</button>
        <button type="button" className="btn-text-danger" aria-label={`删除 ${s.name}`} disabled={busy} onClick={() => onRemove(s)}>删除</button>
      </span>
    </li>
  )
}

function StudentEditor({ s, onSave, onCancel }: {
  s: StudentOut
  onSave: (name: string, no: string) => Promise<void>
  onCancel: () => void
}) {
  const [name, setName] = useState(s.name)
  const [no, setNo] = useState(s.student_no ?? '')
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return setErr('姓名不能为空')
    setSaving(true)
    setErr('')
    try {
      await onSave(name.trim(), no.trim())
    } catch (x) {
      setErr(errorText(x))
      setSaving(false)
    }
  }
  return (
    <li className="student-row editing">
      <form onSubmit={submit} onKeyDown={(e) => { if (e.key === 'Escape') onCancel() }}>
        <div className="field-row">
          <div className="field-block grow">
            <label htmlFor={`sn-${s.id}`}>姓名</label>
            <input id={`sn-${s.id}`} name="name" autoComplete="off" maxLength={64} value={name} autoFocus onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field-block">
            <label htmlFor={`sno-${s.id}`}>学号（可不填）</label>
            <input id={`sno-${s.id}`} name="student-no" autoComplete="off" value={no} onChange={(e) => setNo(e.target.value)} />
          </div>
        </div>
        {err && <p className="err" role="alert">{err}</p>}
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={saving}>保存</button>
          <button type="button" onClick={onCancel}>取消</button>
        </div>
      </form>
    </li>
  )
}

export default function ClassDetail() {
  const { classId } = useParams()
  const id = Number(classId)
  const navigate = useNavigate()
  const location = useLocation()
  const carried = (location.state ?? {}) as { notice?: string; warning?: string }
  const [state, setState] = useState<Load>('loading')
  const [cls, setCls] = useState<ClassOut | null>(null)
  const [students, setStudents] = useState<StudentOut[]>([])
  const [error, setError] = useState(carried.warning ?? '')
  const [notice, setNotice] = useState(carried.notice ?? '')
  const [editing, setEditing] = useState<number | null>(null)
  const [confirm, setConfirm] = useState<null | { kind: 'student'; s: StudentOut } | { kind: 'class' }>(null)
  const [roster, setRoster] = useState('')
  const [busy, setBusy] = useState(false)
  const working = useRef(false)

  const load = useCallback(async () => {
    try {
      const [classes, list] = await Promise.all([
        request<ClassOut[]>('GET', '/api/classes'),
        request<StudentOut[]>('GET', `/api/classes/${id}/students`),
      ])
      const found = classes.find((c) => c.id === id) ?? null
      setCls(found)
      setStudents(list)
      setState(found ? 'ok' : 'notfound')
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return setState('notfound')
      setError(errorText(e))
      setState((old) => (old === 'ok' ? 'ok' : 'error'))
    }
  }, [id])

  useEffect(() => {
    if (!Number.isInteger(id) || id <= 0) return setState('notfound')
    setState('loading')
    void load()
  }, [id, load])

  const rename = async (s: StudentOut, name: string, no: string) => {
    await request('PATCH', `/api/students/${s.id}`, { name, student_no: no || null })
    setEditing(null)
    setNotice('')
    await load()
  }

  const append = async () => {
    if (working.current) return
    const recognized = previewRoster(roster).count
    working.current = true
    setBusy(true)
    setError('')
    try {
      const r = await request<ImportOut>('POST', `/api/classes/${id}/students:import`, { text: roster })
      setRoster('')
      setStudents(r.students)
      setNotice(importNotice(recognized, r.created))
    } catch (e) {
      setError(errorText(e))
    } finally {
      working.current = false
      setBusy(false)
    }
  }

  const confirmed = async () => {
    const c = confirm
    if (!c || working.current) return
    working.current = true
    setBusy(true)
    setError('')
    try {
      if (c.kind === 'student') {
        await request('DELETE', `/api/students/${c.s.id}`)
        setConfirm(null)
        setNotice(`已删除 ${c.s.name}`)
        await load()
      } else {
        await request('DELETE', `/api/classes/${id}`)
        navigate('/', { replace: true })
      }
    } catch (e) {
      // 409 carries the backend's reason (a student who already has results can't be deleted)
      setConfirm(null)
      setNotice('')
      setError(errorText(e))
    } finally {
      working.current = false
      setBusy(false)
    }
  }

  const recognized = previewRoster(roster).count

  if (state !== 'ok') {
    return (
      <>
        <Header />
        <main id="main-content" className="page class-page" tabIndex={-1}>
          <Link to="/" className="back">← 返回班级作业</Link>
          {state === 'loading' && <p className="empty">加载中…</p>}
          {state === 'notfound' && <p className="empty">找不到这个班级（可能不是你的班级，或已经删除）</p>}
          {state === 'error' && (
            <>
              <p className="err" role="alert">{error}</p>
              <button type="button" onClick={() => { setError(''); setState('loading'); void load() }}>重试</button>
            </>
          )}
        </main>
      </>
    )
  }

  return (
    <>
      <Header />
      <main id="main-content" className="page class-page" tabIndex={-1}>
        <Link to={`/?class=${id}`} className="back">← 返回班级作业</Link>
        <div className="page-heading">
          <div>
            <h1>{cls?.name}</h1>
            <p>{cls?.grade} 年级 · 共 {students.length} 人</p>
          </div>
        </div>
        {error && <p className="err" role="alert">{error}</p>}
        {notice && <p className="notice" role="status">{notice}</p>}

        <section className="panel" aria-labelledby="roster-title">
          <h2 id="roster-title" className="serif">学生名单 <span className="count">{students.length}</span></h2>
          {students.length === 0 && <p className="empty">名单还是空的，在下面粘贴名单就能追加</p>}
          {students.length > 0 && (
            <ul className="student-list">
              {students.map((s) =>
                editing === s.id ? (
                  <StudentEditor key={s.id} s={s} onSave={(n, no) => rename(s, n, no)} onCancel={() => setEditing(null)} />
                ) : (
                  <StudentRow key={s.id} s={s} busy={busy} onEdit={(x) => setEditing(x.id)} onRemove={(x) => setConfirm({ kind: 'student', s: x })} />
                ),
              )}
            </ul>
          )}
        </section>

        <section className="panel" aria-labelledby="append-title">
          <h2 id="append-title" className="serif">追加学生</h2>
          <RosterField id="append-roster" label="追加名单" value={roster} onChange={setRoster} />
          <div className="form-actions">
            <button type="button" className="btn-primary" disabled={busy || recognized === 0} onClick={append}>
              {recognized > 0 ? `追加 ${recognized} 人` : '追加'}
            </button>
          </div>
        </section>

        <section className="panel danger-zone" aria-labelledby="danger-title">
          <h2 id="danger-title" className="serif">删除班级</h2>
          <p>班级、名单、作业和成绩会一起删除，无法恢复。</p>
          <button type="button" className="btn-outline-danger" disabled={busy} onClick={() => setConfirm({ kind: 'class' })}>删除班级</button>
        </section>

        {confirm?.kind === 'student' && (
          <Confirm
            title={`删除 ${confirm.s.name}？`}
            message="删除后不能恢复。已有成绩的学生不能删除，可以改名。"
            confirmText="确认删除"
            danger
            onConfirm={confirmed}
            onCancel={() => setConfirm(null)}
          />
        )}
        {confirm?.kind === 'class' && (
          <Confirm
            title={`删除「${cls?.name}」？`}
            message="作业和成绩会一起删除，无法恢复"
            confirmText="确认删除"
            danger
            onConfirm={confirmed}
            onCancel={() => setConfirm(null)}
          />
        )}
      </main>
    </>
  )
}
