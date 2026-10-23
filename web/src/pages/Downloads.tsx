import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Header from '../components/Header'
import { ApiError, errorText, request } from '../lib/api'
import { publishMe } from '../lib/me'
import {
  NAME_MAX, exportAndDownload, exportAndView, needsSignature, openViewerTab, practiceReady,
  type ExportKind, type MeOut,
} from '../lib/download'

export const POPUP_BLOCKED = '浏览器拦住了新窗口，请允许本网站弹出窗口后再点「在线查看」'

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
  // `view`: the pending action shows the PDF in a new tab, which must be opened by the dialog's click
  const [dialog, setDialog] = useState<null | { view: boolean; resume: (win: Window | null) => void }>(null)
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

  /** Download, or show in `win` when one was opened for viewing. */
  const doExport = async (key: string, kind: ExportKind, answers: boolean | undefined, win: Window | null) => {
    setBusyKey(key)
    setError('')
    try {
      if (win) await exportAndView(win, id, kind, answers)
      else await exportAndDownload(id, kind, answers)
    } catch (e) {
      win?.close()
      setError(downloadErrorText(e))
    } finally {
      busy.current = false
      setBusyKey(null)
    }
  }

  const start = async (key: string, kind: ExportKind, answers: boolean | undefined, view: boolean) => {
    if (busy.current) return
    busy.current = true
    setError('')
    // Opened inside the click: a tab opened after an await is blocked by the browser.
    const win = view ? openViewerTab() : null
    if (view && !win) {
      setError(POPUP_BLOCKED)
      busy.current = false
      return
    }
    try {
      const cur = me ?? (await request<MeOut>('GET', '/api/me'))
      setMe(cur)
      if (needsSignature(cur)) {
        win?.close()
        setName('')
        setNameErr('')
        // keep the lock until the dialog is saved or cancelled
        setDialog({ view, resume: (w) => void doExport(key, kind, answers, w) })
        return
      }
    } catch (e) {
      win?.close()
      setError(downloadErrorText(e))
      busy.current = false
      return
    }
    await doExport(key, kind, answers, win)
  }

  const cancelDialog = () => {
    setDialog(null)
    busy.current = false
  }

  const saveName = async () => {
    if (saving.current || !dialog) return
    const n = name.trim()
    if (!n) return setNameErr('请填写署名')
    if (n.length > NAME_MAX) return setNameErr(`署名最多 ${NAME_MAX} 个字`)
    const d = dialog
    // Same rule as `start`: the viewing tab has to come from this click.
    const win = d.view ? openViewerTab() : null
    if (d.view && !win) return setNameErr(POPUP_BLOCKED)
    saving.current = true
    setSaving(true)
    try {
      const m = await request<MeOut>('PATCH', '/api/me', { display_name: n })
      setMe(m)
      publishMe(m) // keep the header's name in sync
      setDialog(null)
      d.resume(win)
    } catch (e) {
      win?.close()
      setNameErr(downloadErrorText(e))
    } finally {
      saving.current = false
      setSaving(false)
    }
  }

  const btn = (key: string, label: string, kind: ExportKind, answers: boolean | undefined, view: boolean,
               disabled = false) => (
    <button
      className={view ? 'dl-btn dl-view' : 'dl-btn'}
      disabled={disabled || busyKey !== null || dialog !== null}
      onClick={() => start(key, kind, answers, view)}
    >
      {busyKey === key ? '正在生成…' : label}
    </button>
  )

  return (
    <>
      <Header />
      <main id="main-content" className="page downloads" tabIndex={-1}>
        <Link to={`/a/${assignmentId}`} className="back">← 返回概览</Link>
        <h1 className="main-title">下载打印</h1>
        <p className="page-description">为课堂准备一份讲评单，为学生留下下一次进步的线索。</p>
        {error && <p className="err" role="alert">{error}</p>}
        <div className="dl-cards">
          <section className="dl-card">
            <h2 className="serif">讲评单</h2>
            <p>按错题整理的课堂讲评材料，不含学生姓名</p>
            <div className="dl-row">
              {btn('lecture-view', '在线查看', 'lecture', undefined, true)}
              {btn('lecture', '下载 PDF', 'lecture', undefined, false)}
            </div>
          </section>
          <section className="dl-card">
            <h2 className="serif">全班错题单</h2>
            <p>每位学生一份的错题清单</p>
            <p className="muted">含学生姓名，请下载后打印</p>
            <div className="dl-row">
              {btn('class_students', '下载 PDF', 'class_students', undefined, false)}
            </div>
          </section>
          <section className="dl-card">
            <h2 className="serif">练习卷</h2>
            {practiceOk === false && <p className="empty">还没有练习卷，请先生成。<Link to={`/a/${assignmentId}/practice`}>去生成练习卷</Link></p>}
            <label className="dl-check">
              <input
                aria-label="PDF 署名"
                name="signature"
                autoComplete="name"
                type="checkbox"
                checked={withAnswers}
                disabled={!practiceOk}
                onChange={(e) => setWithAnswers(e.target.checked)}
              />
              附答案（答案在最后一页）
            </label>
            <div className="dl-row">
              {btn('practice-view', '在线查看', 'practice', withAnswers, true, !practiceOk)}
              {btn('practice', '下载 PDF', 'practice', withAnswers, false, !practiceOk)}
            </div>
          </section>
        </div>
        {dialog && (
          <div className="dl-mask">
            <div className="dl-dialog" role="dialog" aria-label="署名">
              <h2 className="serif">署名</h2>
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
                <button className="dl-btn" disabled={saving_} onClick={saveName}>
                  {dialog.view ? '保存并查看' : '保存并下载'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  )
}
