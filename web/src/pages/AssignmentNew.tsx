import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import { request, errorText } from '../lib/api'
import { subjectsForGrade } from '../lib/subjects'
import type { ClassOut } from '../lib/overview'
import type { MeInfo } from '../lib/me'
export default function AssignmentNew() {
  const { classId } = useParams(),
    navigate = useNavigate()
  const [room, setRoom] = useState<ClassOut>(),
    [title, setTitle] = useState(''),
    [subject, setSubject] = useState('math'),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  const lock = useRef(false)
  useEffect(() => {
    let live = true
    Promise.all([
      request<ClassOut[]>('GET', '/api/classes'),
      request<MeInfo>('GET', '/api/me'),
    ])
      .then(([classes, me]) => {
        if (!live) return
        const found = classes.find((c) => c.id === Number(classId))
        if (!found) {
          setError('找不到这个班级')
          return
        }
        setRoom(found)
        const options = subjectsForGrade(found.grade)
        setSubject(
          options.some((s) => s.value === me.last_subject)
            ? me.last_subject!
            : 'math',
        )
      })
      .catch((e) => live && setError(errorText(e)))
    return () => {
      live = false
    }
  }, [classId])
  return (
    <WorkShell title="新建作业" description={room?.name}>
      <form
        className="work-form"
        onSubmit={async (e) => {
          e.preventDefault()
          if (lock.current || !title.trim() || !room) return
          lock.current = true
          setBusy(true)
          setError('')
          try {
            const a = await request<{ id: number }>(
              'POST',
              '/api/assignments',
              { class_id: room.id, title: title.trim(), subject },
            )
            navigate(`/a/${a.id}/work`)
          } catch (e) {
            setError(errorText(e))
            lock.current = false
            setBusy(false)
          }
        }}
      >
        <label>
          作业名称
          <input
            required
            maxLength={64}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：分数单元练习"
          />
        </label>
        <label>
          学科
          <select value={subject} onChange={(e) => setSubject(e.target.value)}>
            {subjectsForGrade(room?.grade ?? 1).map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <p className="hint">建好后可先上传答案卷，再上传学生试卷。</p>
        {error && (
          <p role="alert" className="err">
            {error}
          </p>
        )}
        <button
          className="btn-primary"
          disabled={!room || busy || !title.trim()}
        >
          {busy ? '正在创建…' : '创建作业'}
        </button>
      </form>
    </WorkShell>
  )
}
