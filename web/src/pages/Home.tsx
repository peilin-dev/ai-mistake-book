import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../components/Header'
import { errorText, request } from '../lib/api'
import { dateText, subjectLabel, type AssignmentOut, type ClassOut } from '../lib/overview'

export default function Home() {
  const [classes, setClasses] = useState<ClassOut[] | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [assignments, setAssignments] = useState<AssignmentOut[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    request<ClassOut[]>('GET', '/api/classes')
      .then((list) => {
        if (!alive) return
        setClasses(list)
        if (list.length) setSelected(list[0].id)
      })
      .catch((e) => alive && setError(errorText(e)))
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (selected === null) return
    let alive = true
    setAssignments(null)
    request<AssignmentOut[]>('GET', `/api/classes/${selected}/assignments`)
      .then((list) => alive && setAssignments([...list].sort((a, b) => b.id - a.id)))
      .catch((e) => alive && setError(errorText(e)))
    return () => {
      alive = false
    }
  }, [selected])

  return (
    <>
      <Header />
      <main className="page home">
        {error && <p className="err">{error}</p>}
        {classes && classes.length === 0 && <p className="empty">还没有班级，请先在小程序里建班</p>}
        {classes && classes.length > 0 && (
          <div className="home-grid">
            <nav className="class-list" aria-label="班级">
              {classes.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={c.id === selected ? 'class-item active' : 'class-item'}
                  aria-current={c.id === selected ? 'true' : undefined}
                  onClick={() => setSelected(c.id)}
                >
                  {c.name}
                </button>
              ))}
            </nav>
            <section className="assignment-list">
              {assignments === null && !error && <p className="empty">加载中…</p>}
              {assignments && assignments.length === 0 && <p className="empty">这个班还没有作业</p>}
              {assignments?.map((a) => (
                <Link key={a.id} to={`/a/${a.id}`} className="assignment-item">
                  <span className="title">{a.title}</span>
                  <span className="meta">
                    {subjectLabel(a.subject)}
                    {dateText(a.created_at) && ` · ${dateText(a.created_at)}`}
                  </span>
                </Link>
              ))}
            </section>
          </div>
        )}
      </main>
    </>
  )
}
