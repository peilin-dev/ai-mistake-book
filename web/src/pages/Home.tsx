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
    return () => { alive = false }
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
      .then(list => alive && setAssignments([...list].sort((a, b) => b.id - a.id)))
      .catch(e => alive && setError(errorText(e)))
    return () => { alive = false }
  }, [selected])

  const activeClass = classes?.find(c => c.id === selected)
  const subjects = [...new Set(assignments?.map(a => a.subject) ?? [])]
  const visible = assignments?.filter(a => (!subject || a.subject === subject) && a.title.toLowerCase().includes(query.trim().toLowerCase()))
  const classView = params.get('view') === 'classes'
  return (
    <>
      <Header />
      <main id="main-content" className="page home" tabIndex={-1}>
        <div className="page-heading">
          <div><h1>{classView ? '我的班级' : '班级作业'}</h1><p>{classView ? '管理班级和学生名单，开始新一轮教学。' : '从一份作业开始，完成批改、复核与讲评。'}</p></div>
          <Link to={classView || !activeClass ? '/classes/new' : `/classes/${activeClass.id}/assignments/new`} className="btn-primary"><Icon name="plus" size={18} />{classView || !activeClass ? '新建班级' : '新建作业'}</Link>
        </div>
        {error && <p className="err" role="alert">{error}</p>}
        {classes === null && !error && <p className="empty">加载中…</p>}
        {classes && classes.length === 0 && <div className="empty empty-start"><Icon name="users" size={32} /><h2>从第一个班级开始</h2><p>还没有班级，先建一个，把名单粘贴进来就能开始。</p></div>}
        {classes && classView && classes.length > 0 && <section aria-label="班级列表" className="class-directory">{classes.map(c => <article className="class-card" key={c.id}>
          <span className="card-icon"><Icon name="users" size={23} /></span><h2>{c.name}</h2><p>{c.grade >= 7 ? '初中' : '小学'} · {c.grade} 年级</p><div className="class-card-actions"><Link to={`/?class=${c.id}`}>查看作业 <Icon name="arrow" size={16} /></Link><Link to={`/classes/${c.id}`}>管理名单</Link></div>
        </article>)}</section>}
        {classes && classes.length > 0 && !classView && <section className="workspace" aria-label="班级作业">
          <div className="class-switcher-row"><nav className="class-switcher" aria-label="班级">{classes.map(c => <button key={c.id} type="button" aria-pressed={c.id === selected} onClick={() => { setSelected(c.id); setParams({ class: String(c.id) }, { replace: true }) }}>{c.name}</button>)}</nav><Link to="/classes/new" className="class-add" aria-label="新建班级"><Icon name="plus" size={18} /></Link></div>
          <div className="section-heading assignments-heading"><div><h2><Icon name="layers" size={22} />{activeClass?.name || '班级作业'}<span className="count">{assignments?.length ?? '—'} 份作业</span></h2><p>{activeClass?.grade} 年级 · 上传卷子后可查看批改进度和学生成绩。</p></div>{activeClass && <Link to={`/classes/${activeClass.id}`} className="manage-link"><Icon name="users" size={16} />管理名单</Link>}</div>
          <div className="assignment-toolbar"><div className="subject-filters" aria-label="学科筛选"><button type="button" aria-pressed={!subject} onClick={() => setFilter('subject', '')}>全部学科</button>{subjects.map(s => <button type="button" key={s} aria-pressed={subject === s} onClick={() => setFilter('subject', s)}>{subjectLabel(s)}</button>)}</div><span className="sort-label">按创建时间 · 最新优先</span></div>
          {query && <div className="search-summary"><span>“{query}” 的搜索结果</span><button type="button" onClick={() => setFilter('q', '')}>清除搜索</button></div>}
          <div className="assignment-list" aria-live="polite" aria-busy={assignments === null && !error}>
            {assignments === null && !error && <p className="empty">加载中…</p>}
            {assignments && assignments.length === 0 && <div className="empty"><Icon name="file" size={30} /><h3>这个班还没有作业</h3><p>点击右上角“新建作业”，开始第一次批改。</p></div>}
            {assignments && assignments.length > 0 && visible?.length === 0 && <div className="empty"><p>没有找到匹配的作业</p><button type="button" onClick={() => setParams(selected ? { class: String(selected) } : {}, { replace: true })}>清除筛选</button></div>}
            {visible?.map(a => <Link key={a.id} to={`/a/${a.id}/work`} className={`assignment-item subject-${a.subject}`}>
              <span className="card-top"><span className="card-icon"><Icon name={a.subject === 'math' || a.subject === 'physics' ? 'clipboard' : a.subject === 'chinese' || a.subject === 'english' ? 'book' : 'file'} size={23} /></span><span className="subject-tag">{subjectLabel(a.subject)}</span></span>
              <span className="assignment-copy"><span className="title">{a.title}</span><span className="assignment-description">答案核对、试卷批改、成绩与学情</span></span>
              <span className="card-bottom"><span className="meta">{dateText(a.created_at) || '作业日期未记录'}</span><span className="row-action">处理作业 <Icon name="arrow" size={17} /></span></span>
            </Link>)}
          </div>
          <p className="workspace-footnote"><Icon name="check" size={15} />电脑上传卷子，核对批改结果，再进入学情讲评。</p>
        </section>}
      </main>
    </>
  )
}
