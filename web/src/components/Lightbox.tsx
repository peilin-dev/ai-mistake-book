import { useEffect } from 'react'

/** Full-screen image viewer; Esc or a click anywhere closes it. */
export default function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])
  return (
    <div className="lightbox" role="dialog" aria-label="放大查看" onClick={onClose}>
      <img src={src} alt="学生作答原图" />
    </div>
  )
}
