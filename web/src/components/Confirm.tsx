import { useEffect, useId, useRef } from 'react'

export interface ConfirmProps {
  title: string
  message: string
  confirmText: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Generic two-button confirmation. The safe button ("取消") has focus; Esc and a click outside cancel. */
export default function Confirm({ title, message, confirmText, danger, onConfirm, onCancel }: ConfirmProps) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  const descId = useId()

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null
    cancelRef.current?.focus()
    return () => before?.focus?.()
  }, [])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onCancel()
    } else if (e.key === 'Tab') {
      // keep focus inside the dialog
      const first = cancelRef.current
      const last = confirmRef.current
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
    }
  }

  return (
    <div className="dl-mask" onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}>
      <div
        className="dl-dialog confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        onKeyDown={onKeyDown}
      >
        <h2 id={titleId} className="serif">{title}</h2>
        <p id={descId}>{message}</p>
        <div className="confirm-actions">
          <button type="button" ref={cancelRef} onClick={onCancel}>取消</button>
          <button
            type="button"
            ref={confirmRef}
            className={danger ? 'btn-primary btn-danger' : 'btn-primary'}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
