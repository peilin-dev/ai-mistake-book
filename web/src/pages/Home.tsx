import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Header from '../components/Header'
import Icon from '../components/Icon'
import { errorText, request } from '../lib/api'
import { dateText, subjectLabel, type AssignmentOut, type ClassOut } from '../lib/overview'

export default function Home() {
  const [classes, setClasses] = useState<ClassOut[] | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [assignments, setAssignments] = useState<AssignmentOut[] | null>(null)
  const [error, setError] = useState('')
  const [params, setParams] = useSearchParams()
  const query = params.get('q') || ''
  const subject = params.get('subject') || ''
  const classId = Number(params.get('class')) || null
  const setFilter = (key: string, value: string) => {
    setParams((old) => { const next = new URLSearchParams(old); value ? next.set(key, value) : next.delete(key); return next }, { replace: true })
  }

  useEffect(() => {
    let alive = true
    request<ClassOut[]>('GET', '/api/classes')
      .then((list) => {
        if (!alive) return
        setClasses(list)
        if (list.length) setSelected(list.find(c => c.id === classId)?.id ?? list[0].id)
      })
      .catch((e) => alive && setError(errorText(e)))
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (classes?.length) setSelected(classes.find(c => c.id === classId)?.id ?? classes[0].id)
  }, [classId, classes])

  useEffect(() => {
    if (selected === null) return
    let alive = true
    setAssignments(null)
    setError('')
    request<AssignmentOut[]>('GET', `/api/classes/${selected}/assignments`)
      .then((list) => alive && setAssignments([...list].sort((a, b) => b.id - a.id)))
      .catch((e) => alive && setError(errorText(e)))
    return () => {
      alive = false
    }
  }, [selected])

  const activeClass = classes?.find(c => c.id === selected)
  const subjects = [...new Set(assignments?.map(a => a.subject) ?? [])]
  const visible = assignments?.filter(a => (!subject || a.subject === subject) && a.title.toLowerCase().includes(query.trim().toLowerCase()))

  return (
    <>
      <Header />
      <main id="main-content" className="page home" tabIndex={-1}>
        {error && <p className="err" role="alert">{error}</p>}
        {classes === null && !error && <p className="empty">加载中…</p>}
        {classes && classes.length === 0 && <p className="empty">还没有班级，请先在小程序里建班</p>}
        {classes && classes.length > 0 && (
          <div className="home-grid">
            <aside className="class-sidebar">
            <div className="sidebar-title"><Icon name="book" size={18} /><h2>我的班级</h2><span>{classes.length}</span></div>
            <nav className="class-list" aria-label="班级">
              {classes.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={c.id === selected ? 'class-item active' : 'class-item'}
                  aria-current={c.id === selected ? 'true' : undefined}
                  onClick={() => { setSelected(c.id); setParams({ class: String(c.id) }, { replace: true }) }}
                >
                  <span>{c.name}</span><small>{c.grade} 年级</small>
                </button>
              ))}
            </nav>
            <div className="sidebar-note"><Icon name="pen" size={20} /><p>手机拍卷，电脑讲评。</p><span>同一份作业，两端同步。</span></div>
            </aside>
            <section className="workspace" aria-label="班级作业">
            <div className="page-heading"><div><h1>{activeClass?.name || '班级作业'}</h1><p>整理每一次练习，看见每一点进步。</p></div><span className="quiet-label">{activeClass?.grade} 年级</span></div>
            <div className="section-heading"><h2 className="serif">全部作业 <span className="count">{assignments?.length ?? '—'}</span></h2><label className="search-field"><Icon name="search" size={18} /><input type="search" name="assignment-search" autoComplete="off" aria-label="搜索作业" placeholder="搜索作业名称…" value={query} onChange={e => setFilter('q', e.target.value)} /></label></div>
            <div className="subject-filters" aria-label="学科筛选"><button type="button" aria-pressed={!subject} onClick={() => setFilter('subject', '')}>全部学科</button>{subjects.map(s => <button type="button" key={s} aria-pressed={subject === s} onClick={() => setFilter('subject', s)}>{subjectLabel(s)}</button>)}</div>
            <div className="assignment-list" aria-live="polite" aria-busy={assignments === null && !error}>
              {assignments === null && !error && <p className="empty">加载中…</p>}
              {assignments && assignments.length === 0 && <p className="empty">这个班还没有作业</p>}
              {assignments && assignments.length > 0 && visible?.length === 0 && <div className="empty"><p>没有找到匹配的作业</p><button type="button" onClick={() => setParams(selected ? { class: String(selected) } : {}, { replace: true })}>清除筛选</button></div>}
              {visible?.map((a) => (
                <Link key={a.id} to={`/a/${a.id}`} className="assignment-item">
                  <span className="subject-tag">{subjectLabel(a.subject)}</span>
                  <span className="assignment-copy"><span className="title">{a.title}</span><span className="meta">{dateText(a.created_at) || '查看批改结果与班级学情'}</span></span>
                  <span className="row-action">查看学情 <Icon name="arrow" size={18} /></span>
                </Link>
              ))}
            </div>
            <p className="workspace-footnote">新建班级、拍照上传与批改复核，请在红笔君小程序中完成。</p>
            </section>
          </div>
        )}
      </main>
    </>
  )
}
