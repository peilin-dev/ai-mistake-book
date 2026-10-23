import { useEffect, useId, useRef, useState } from 'react'
import { errorText, request } from '../lib/api'
import { NAME_MAX } from '../lib/download'
import { publishMe, type MeInfo } from '../lib/me'

/**
 * Account settings. Each concern is its own `<section className="acct-section">`;
 * Task 11 adds the login name / password section next to 署名 without touching the shell.
 */
export default function AccountDialog({ me, onClose }: { me: MeInfo; onClose: () => void }) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const saving = useRef(false)
  const [name, setName] = useState(me.display_name ?? '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null
    inputRef.current?.focus()
    return () => before?.focus?.()
  }, [])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
    } else if (e.key === 'Tab') {
      const items = dialogRef.current?.querySelectorAll<HTMLElement>('input,button:not([disabled])')
      if (!items || items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
  }

  const save = async () => {
    if (saving.current) return
    const n = name.trim()
    if (!n) return setErr('请填写署名')
    if (n.length > NAME_MAX) return setErr(`署名最多 ${NAME_MAX} 个字`)
    saving.current = true
    setBusy(true)
    setErr('')
    try {
      const m = await request<MeInfo>('PATCH', '/api/me', { display_name: n })
      publishMe(m)
      onClose()
    } catch (e) {
      setErr(errorText(e))
      saving.current = false
      setBusy(false)
    }
  }

  const quota = me.quota_total !== undefined && me.quota_used !== undefined
    ? `本月已批改 ${me.quota_used} / ${me.quota_total} 页`
    : ''

  return (
    <div className="dl-mask" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div
        ref={dialogRef}
        className="dl-dialog acct"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
      >
        <h2 id={titleId} className="serif">账号设置</h2>
        <section className="acct-section">
          <label htmlFor={`${titleId}-name`}>署名</label>
          <input
            id={`${titleId}-name`}
            ref={inputRef}
            value={name}
            placeholder="例如 王老师"
            autoComplete="name"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void save() }}
          />
          <p className="acct-hint">PDF 上印的署名，小程序和网页同时生效</p>
          {err && <p className="err" role="alert">{err}</p>}
        </section>
        {quota && (
          <section className="acct-section">
            <p className="acct-quota">{quota}</p>
          </section>
        )}
        <div className="confirm-actions">
          <button type="button" onClick={onClose}>取消</button>
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void save()}>保存</button>
        </div>
      </div>
    </div>
  )
}
