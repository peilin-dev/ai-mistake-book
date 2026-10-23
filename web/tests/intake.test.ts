import { describe, expect, it, vi, afterEach } from 'vitest'
import { zipSync, strToU8, unzipSync } from 'fflate'
import {
  expandFiles,
  sortPages,
  toJpeg,
  type SourcePage,
} from '../src/lib/intake'
const page = (
  fileName: string,
  takenAt: number | null = null,
  pageNo: number | null = null,
): SourcePage => ({
  id: fileName,
  fileName,
  takenAt,
  pageNo,
  load: async () => new Blob(),
})
// jsdom's File predates Blob.arrayBuffer.
function file(bytes: Uint8Array, name: string) {
  const f = new File([bytes], name)
  f.arrayBuffer = async () => new Uint8Array(bytes).buffer
  return f
}
afterEach(() => vi.restoreAllMocks())
describe('file intake', () => {
  it('sorts capture times first, then natural file names and PDF page numbers', () => {
    const list = sortPages([
      page('IMG_10.jpg'),
      page('paper.pdf', null, 10),
      page('IMG_2.jpg'),
      page('b.jpg', 20),
      page('paper.pdf', null, 2),
      page('a.jpg', 10),
    ])
    expect(list.map((p) => [p.fileName, p.pageNo])).toEqual([
      ['a.jpg', null],
      ['b.jpg', null],
      ['IMG_2.jpg', null],
      ['IMG_10.jpg', null],
      ['paper.pdf', 2],
      ['paper.pdf', 10],
    ])
  })
  it('reports unsupported files and retains supported photos', async () => {
    const out = await expandFiles([
      file(new Uint8Array(), 'a.txt'),
      file(new Uint8Array(), 'photo.jpg'),
    ])
    expect(out.pages).toHaveLength(1)
    expect(out.bad).toEqual([{ fileName: 'a.txt', reason: '不支持的文件格式' }])
  })
  it('ignores hidden, system and unsupported ZIP entries', async () => {
    const zip = zipSync({
      '__MACOSX/x.jpg': new Uint8Array([120]),
      '.hidden.jpg': new Uint8Array([120]),
      'folder/.foo/x.jpg': new Uint8Array([120]),
      'folder/IMG_2.jpg': new Uint8Array([120]),
      'note.txt': new Uint8Array([120]),
    })
    expect(Object.keys(unzipSync(zip))).toContain('folder/IMG_2.jpg')
    const out = await expandFiles([file(zip, 'photos.zip')])
    expect(out.bad).toEqual([])
    expect(out.pages.map((p) => p.fileName)).toEqual([
      'photos.zip/folder/IMG_2.jpg',
    ])
  })
  it('reports a broken archive while keeping the other files', async () => {
    const out = await expandFiles([
      file(strToU8('broken'), 'bad.zip'),
      file(new Uint8Array(), 'good.png'),
    ])
    expect(out.pages).toHaveLength(1)
    expect(out.bad[0].reason).toBe('压缩包打不开')
  })
  it('converts a large image to JPEG at at most 2000 pixels', async () => {
    const draw = vi.fn(),
      fill = vi.fn()
    vi.stubGlobal(
      'Image',
      class {
        naturalWidth = 4000
        naturalHeight = 3000
        onload?: () => void
        set src(_: string) {
          queueMicrotask(() => this.onload?.())
        }
      },
    )
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:test'),
      revokeObjectURL: vi.fn(),
    })
    const canvas = document.createElement('canvas')
    vi.spyOn(canvas, 'getContext').mockReturnValue({
      drawImage: draw,
      fillRect: fill,
    } as unknown as CanvasRenderingContext2D)
    vi.spyOn(canvas, 'toBlob').mockImplementation((cb) =>
      cb(new Blob(['jpeg'], { type: 'image/jpeg' })),
    )
    vi.spyOn(document, 'createElement').mockReturnValue(canvas)
    const blob = new Blob(['image'])
    blob.slice = () =>
      ({ arrayBuffer: async () => new ArrayBuffer(16) }) as Blob
    await toJpeg(blob)
    expect(canvas.width).toBe(2000)
    expect(canvas.height).toBe(1500)
    expect(draw).toHaveBeenCalledWith(expect.anything(), 0, 0, 2000, 1500)
    vi.unstubAllGlobals()
  })
})
