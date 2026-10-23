import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import RosterField from '../components/RosterField'
import { errorText, request } from '../lib/api'
import { DEFAULT_GRADE, GRADE_LABELS, defaultClassName } from '../lib/grades'
import { previewRoster } from '../lib/roster'
import { importNotice, type ClassOut, type ImportOut } from '../lib/classes'

export default function ClassNew() {
  const navigate = useNavigate()
  const [grade, setGrade] = useState(DEFAULT_GRADE)
  const [name, setName] = useState(defaultClassName(DEFAULT_GRADE))
  const [nameTouched, setNameTouched] = useState(false)
  const [roster, setRoster] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const count = previewRoster(roster).count

  const pickGrade = (g: number) => {
    setGrade(g)
    if (!nameTouched) setName(defaultClassName(g))
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const className = name.trim()
    if (!className) return setError('请先填写班级名称')
    if (submitting.current) return
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      const cls = await request<ClassOut>('POST', '/api/classes', { name: className, grade })
      let notice = ''
      let warning = ''
      if (count > 0) {
        try {
          const r = await request<ImportOut>('POST', `/api/classes/${cls.id}/students:import`, { text: roster })
          notice = importNotice(count, r.created)
        } catch (err) {
          warning = `班级已建好，但名单还没导入成功：${errorText(err)}。可以在这里重新追加。`
        }
      }
      navigate(`/classes/${cls.id}`, { state: { notice, warning } })
    } catch (err) {
      setError(errorText(err))
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  return (
    <>
      <Header />
      <main id="main-content" className="page class-form-page" tabIndex={-1}>
        <Link to="/" className="back">← 返回班级作业</Link>
        <h1 className="main-title">新建班级</h1>
        <p className="page-description">填好年级和名称，把名单粘贴进来就能开始；名单也可以之后再追加。</p>
        {error && <p className="err" role="alert">{error}</p>}
        <form className="form-card" onSubmit={submit}>
          <div className="field-row">
            <div className="field-block">
              <label htmlFor="grade">年级</label>
              <select id="grade" name="grade" value={grade} onChange={(e) => pickGrade(Number(e.target.value))}>
                {GRADE_LABELS.map((l, i) => <option key={l} value={i + 1}>{l}</option>)}
              </select>
            </div>
            <div className="field-block grow">
              <label htmlFor="class-name">班级名称</label>
              <input
                id="class-name"
                name="class-name"
                autoComplete="off"
                maxLength={32}
                value={name}
                onChange={(e) => { setName(e.target.value); setNameTouched(true) }}
              />
            </div>
          </div>
          <RosterField id="roster" label="学生名单（可以先不填）" value={roster} onChange={setRoster} />
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? '正在建班…' : count > 0 ? `建班并导入 ${count} 人` : '建班'}
            </button>
            <Link to="/" className="btn-quiet">取消</Link>
          </div>
        </form>
      </main>
    </>
  )
}
