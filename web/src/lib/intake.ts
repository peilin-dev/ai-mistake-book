export const MAX_BATCH = 200
export const ACCEPT = '.jpg,.jpeg,.png,.webp,.heic,.heif,.pdf,.zip'
export type SourcePage = {
  id: string
  fileName: string
  pageNo: number | null
  takenAt: number | null
  load: () => Promise<Blob>
}
export type BadFile = { fileName: string; reason: string }
let sequence = 0
const ext = (name: string) => name.split('.').pop()?.toLowerCase() ?? ''
const imageExt = ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif']
async function pdfLibrary() {
  const pdf = await import('pdfjs-dist')
  const { default: worker } = await import(
    'pdfjs-dist/build/pdf.worker.min.mjs?url'
  )
  pdf.GlobalWorkerOptions.workerSrc = worker
  return pdf
}
function canvasBlob(canvas: HTMLCanvasElement, quality = 0.85): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('图片转换失败'))),
      'image/jpeg',
      quality,
    ),
  )
}
export async function expandFiles(
  files: File[],
): Promise<{ pages: SourcePage[]; bad: BadFile[] }> {
  const pages: SourcePage[] = [],
    bad: BadFile[] = []
  async function add(file: File, nested = false) {
    const kind = ext(file.name)
    try {
      if (kind === 'zip' && !nested) {
        const { unzipSync } = await import('fflate')
        let expandedBytes = 0
        let acceptedEntries = 0
        const entries = unzipSync(new Uint8Array(await file.arrayBuffer()), {
          filter: (f) => {
            const supported =
              !f.name
                .split('/')
                .some((s) => s.startsWith('.') || s === '__MACOSX') &&
              [...imageExt, 'pdf'].includes(ext(f.name))
            if (!supported) return false
            if (
              f.originalSize > 100 * 1024 * 1024 ||
              expandedBytes + f.originalSize > 200 * 1024 * 1024
            ) {
              bad.push({
                fileName: `${file.name}/${f.name}`,
                reason: '解压后的文件过大，请拆分后上传',
              })
              return false
            }
            if (acceptedEntries >= MAX_BATCH + 1) return false
            acceptedEntries++
            expandedBytes += f.originalSize
            return true
          },
        })
        for (const [name, bytes] of Object.entries(entries)) {
          await add(
            new File([new Uint8Array(bytes)], `${file.name}/${name}`),
            true,
          )
          if (pages.length > MAX_BATCH) break
        }
      } else if (kind === 'pdf') {
        const pdf = await pdfLibrary()
        const document = await pdf.getDocument({
          data: new Uint8Array(await file.arrayBuffer()),
        }).promise
        const count = document.numPages
        await document.destroy()
        for (let n = 1; n <= count && pages.length <= MAX_BATCH; n++) {
          const pageNo = n
          pages.push({
            id: `page-${++sequence}`,
            fileName: file.name,
            pageNo,
            takenAt: null,
            load: async () => {
              const doc = await pdf.getDocument({
                data: new Uint8Array(await file.arrayBuffer()),
              }).promise
              try {
                const page = await doc.getPage(pageNo),
                  original = page.getViewport({ scale: 1 })
                const viewport = page.getViewport({
                  scale: 2000 / Math.max(original.width, original.height),
                })
                const canvas = documentElement()
                canvas.width = Math.ceil(viewport.width)
                canvas.height = Math.ceil(viewport.height)
                await page.render({
                  canvasContext: canvas.getContext('2d')!,
                  viewport,
                }).promise
                return await canvasBlob(canvas)
              } finally {
                await doc.destroy()
              }
            },
          })
        }
      } else if (imageExt.includes(kind)) {
        let takenAt: number | null = null
        try {
          const { parse } = await import('exifr')
          const meta = await parse(file, ['DateTimeOriginal'])
          const date = meta?.DateTimeOriginal
          if (date instanceof Date && Number.isFinite(+date)) takenAt = +date
        } catch {
          /* optional metadata */
        }
        pages.push({
          id: `page-${++sequence}`,
          fileName: file.name,
          pageNo: null,
          takenAt,
          load: async () => file,
        })
      } else if (!nested)
        bad.push({ fileName: file.name, reason: '不支持的文件格式' })
    } catch {
      bad.push({
        fileName: file.name,
        reason:
          kind === 'pdf'
            ? '这个 PDF 打不开'
            : kind === 'zip'
              ? '压缩包打不开'
              : '这张图片打不开',
      })
    }
  }
  for (const file of files) {
    await add(file)
    if (pages.length > MAX_BATCH) break
  }
  return { pages: sortPages(pages), bad }
}
const documentElement = () => document.createElement('canvas')
export function sortPages(pages: SourcePage[]): SourcePage[] {
  return [...pages].sort((a, b) => {
    if (a.takenAt !== null || b.takenAt !== null) {
      if (a.takenAt === null) return 1
      if (b.takenAt === null) return -1
      if (a.takenAt !== b.takenAt) return a.takenAt - b.takenAt
    }
    return (
      a.fileName.localeCompare(b.fileName, 'zh-CN', { numeric: true }) ||
      (a.pageNo ?? 0) - (b.pageNo ?? 0)
    )
  })
}
export async function toJpeg(
  input: Blob,
  maxSide = 2000,
  quality = 0.85,
): Promise<Blob> {
  let blob = input
  const header = new Uint8Array(await input.slice(0, 16).arrayBuffer())
  const isHeic =
    ['heic', 'heif'].some((t) => input.type.includes(t)) ||
    String.fromCharCode(...header.slice(4, 8)) === 'ftyp'
  if (isHeic) {
    try {
      const { default: convert } = await import('heic2any')
      const result = await convert({ blob, toType: 'image/jpeg', quality })
      blob = Array.isArray(result) ? result[0] : result
    } catch {
      throw new Error('这张 HEIC 图片解码失败')
    }
  }
  const url = URL.createObjectURL(blob)
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('这张图片打不开'))
      img.src = url
    })
    const scale = Math.min(
      1,
      maxSide / Math.max(image.naturalWidth, image.naturalHeight),
    )
    const canvas = documentElement()
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    return await canvasBlob(canvas, quality)
  } finally {
    URL.revokeObjectURL(url)
  }
}
export async function prepareOne(file: File): Promise<Blob> {
  if (!imageExt.includes(ext(file.name))) throw new Error('请选择一张图片')
  return toJpeg(file)
}
export function imageBody(blob: Blob) {
  const data = new FormData()
  data.append('file', blob, 'page.jpg')
  return data
}
