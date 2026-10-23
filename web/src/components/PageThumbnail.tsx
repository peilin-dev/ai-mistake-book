import { useEffect, useState } from 'react'
import { toJpeg, type SourcePage } from '../lib/intake'
// Preview pages mount only when scrolled near the viewport; each conversion is
// released after completion and object URLs are revoked on unmount.
export default function PageThumbnail({ page }: { page: SourcePage }) {
  const [url, setUrl] = useState(''),
    [error, setError] = useState(''),
    [node, setNode] = useState<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!node) return
    let live = true,
      objectUrl = '',
      started = false
    const load = async () => {
      if (started) return
      started = true
      try {
        const blob = await toJpeg(await page.load(), 320, 0.7)
        if (live) {
          objectUrl = URL.createObjectURL(blob)
          setUrl(objectUrl)
        }
      } catch {
        if (live) setError('预览失败，请检查图片')
      }
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          observer.disconnect()
          void load()
        }
      },
      { rootMargin: '200px' },
    )
    observer.observe(node)
    return () => {
      live = false
      observer.disconnect()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [page, node])
  return (
    <div ref={setNode} className="page-thumb">
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          aria-label={`查看 ${page.fileName} 预览`}
        >
          <img
            src={url}
            alt={`${page.fileName}${page.pageNo ? ` 第 ${page.pageNo} 页` : ''}`}
          />
        </a>
      ) : (
        <span>{error || '正在准备预览…'}</span>
      )}
    </div>
  )
}
