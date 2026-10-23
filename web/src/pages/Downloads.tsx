import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Header from '../components/Header'
import { ApiError, errorText, request } from '../lib/api'
import {
  NAME_MAX, exportAndDownload, needsSignature, practiceReady,
  type ExportKind, type MeOut,
} from '../lib/download'

function downloadErrorText(e: unknown): string {
  if (e instanceof ApiError && e.status === 409 && e.detail) return e.detail
  return errorText(e)
}

export default function Downloads() {
  const { assignmentId } = useParams()
  const id = Number(assignmentId)
  const [me, setMe] = useState<MeOut | null>(null)
  const [practiceOk, setPracticeOk] = useState<boolean | null>(null)
  const [withAnswers, setWithAnswers] = useState(true)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [dialog, setDialog] = useState<null | { resume: () => void }>(null)
  const [name, setName] = useState('')
  const [nameErr, setNameErr] = useState('')
  const busy = useRef(false)
  const saving = useRef(false)
  const [saving_, setSaving] = useState(false)

  useEffect(() => {
    let alive = true
    setPracticeOk(null)
    request<MeOut>('GET', '/api/me').then((m) => alive && setMe(m)).catch(() => {})
    practiceReady(id)
      .then((ok) => alive && setPracticeOk(ok))
      .catch(() => alive && setPracticeOk(false))
    return () => {
      alive = false
    }
  }, [id])

  const doExport = async (key: string, kind: ExportKind, answers?: boolean) => {
    setBusyKey(key)
    setError('')
    try {
      await exportAndDownload(id, kind, answers)
    } catch (e) {
      setError(downloadErrorText(e))
    } finally {
      busy.current = false
      setBusyKey(null)
    }
  }

  const start = async (key: string, kind: ExportKind, answers?: boolean) => {
    if (busy.current) return
    busy.current = true
    setError('')
    try {
      const cur = me ?? (await request<MeOut>('GET', '/api/me'))
      setMe(cur)
      if (needsSignature(cur)) {
        setName('')
        setNameErr('')
        // keep the lock until the dialog is saved or cancelled
        setDialog({ resume: () => void doExport(key, kind, answers) })
        return
      }
    } catch (e) {
      setError(downloadErrorText(e))
      busy.current = false
      return
    }
    await doExport(key, kind, answers)
  }

  const cancelDialog = () => {
    setDialog(null)
    busy.current = false
  }

  const saveName = async () => {
    if (saving.current) return
    const n = name.trim()
    if (!n) return setNameErr('请填写署名')
    if (n.length > NAME_MAX) return setNameErr(`署名最多 ${NAME_MAX} 个字`)
    saving.current = true
    setSaving(true)
    try {
      const m = await request<MeOut>('PATCH', '/api/me', { display_name: n })
      setMe(m)
      const d = dialog
      setDialog(null)
      d?.resume()
    } catch (e) {
      setNameErr(downloadErrorText(e))
    } finally {
      saving.current = false
      setSaving(false)
    }
  }

  const btn = (key: string, label: string, kind: ExportKind, answers?: boolean, disabled = false) => (
    <button
      className="dl-btn"
      disabled={disabled || busyKey !== null || dialog !== null}
      onClick={() => start(key, kind, answers)}
    >
      {busyKey === key ? '正在生成…' : label}
    </button>
  )

  return (
    <>
      <Header />
      <main className="page downloads">
        <Link to={`/a/${assignmentId}`} className="back">← 返回概览</Link>
        <h1 className="main-title">下载打印</h1>
        {error && <p className="err">{error}</p>}
        <div className="dl-cards">
          <section className="dl-card">
            <h2>讲评单</h2>
            <p>按错题整理的课堂讲评材料</p>
            {btn('lecture', '下载 PDF', 'lecture')}
          </section>
          <section className="dl-card">
            <h2>全班错题单</h2>
            <p>每位学生一份的错题清单</p>
            {btn('class_students', '下载 PDF', 'class_students')}
          </section>
          <section className="dl-card">
            <h2>练习卷</h2>
            {practiceOk === false && <p className="empty">练习卷请先在手机上生成</p>}
            <div className="dl-row">
              {btn('practice-yes', '附答案', 'practice', true, !practiceOk)}
              {btn('practice-no', '不附答案', 'practice', false, !practiceOk)}
            </div>
          </section>
        </div>
        {dialog && (
          <div className="dl-mask">
            <div className="dl-dialog" role="dialog" aria-label="署名">
              <h2>署名</h2>
              <p>PDF 上会印上这个署名</p>
              <input
                value={name}
                placeholder="例如 王老师"
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
              {nameErr && <p className="err">{nameErr}</p>}
              <div className="dl-row">
                <button onClick={cancelDialog}>取消</button>
                <button className="dl-btn" disabled={saving_} onClick={saveName}>保存并下载</button>
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  )
}
