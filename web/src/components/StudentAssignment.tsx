import { useEffect, useRef, useState } from 'react'
import { errorText, request } from '../lib/api'
export default function StudentAssignment({
  assignmentId,
  pageId,
  onSaved,
}: {
  assignmentId: string
  pageId: number
  onSaved: () => void
}) {
  const [students, setStudents] = useState<{ id: number; name: string }[]>([])
  const [selected, setSelected] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const lock = useRef(false)
  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        const a = await request<{ class_id: number }>(
          'GET',
          `/api/assignments/${assignmentId}`,
        )
        const list = await request<{ id: number; name: string }[]>(
          'GET',
          `/api/classes/${a.class_id}/students`,
        )
        if (live) setStudents(list)
      } catch (e) {
        if (live) setError(errorText(e))
      }
    })()
    return () => {
      live = false
    }
  }, [assignmentId])
  return (
    <section className="notice">
      <h3>学生归属不对？</h3>
      <p className="hint">更改归属会移动整张卷子的批改结果，请先核对原图。</p>
      <div className="work-actions">
        <label>
          卷子属于
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">选择正确的学生</option>
            {students.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={busy || !selected}
          onClick={async () => {
            if (lock.current || !selected) return
            lock.current = true
            setBusy(true)
            setError('')
            try {
              await request('PATCH', `/api/pages/${pageId}`, {
                student_id: Number(selected),
              })
              onSaved()
            } catch (e) {
              setError(errorText(e))
            } finally {
              lock.current = false
              setBusy(false)
            }
          }}
        >
          确认更改归属
        </button>
      </div>
      {error && (
        <p className="err" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
