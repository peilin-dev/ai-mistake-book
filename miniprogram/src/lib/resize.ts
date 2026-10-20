import Taro from '@tarojs/taro'

/** Scale so the long edge is at most maxLong; never enlarge. */
export function targetSize(w: number, h: number, maxLong = 2000): { width: number; height: number } {
  const long = Math.max(w, h)
  if (long <= maxLong) return { width: Math.round(w), height: Math.round(h) }
  const k = maxLong / long
  return { width: Math.max(1, Math.round(w * k)), height: Math.max(1, Math.round(h * k)) }
}

/**
 * Page-side only (offscreen canvas, not unit-tested): draw the photo at
 * targetSize and export as JPEG quality 0.85. Returns a temp file path.
 */
export async function compressForUpload(path: string): Promise<string> {
  const info = await Taro.getImageInfo({ src: path })
  const { width, height } = targetSize(info.width, info.height)
  const canvas = Taro.createOffscreenCanvas({ type: '2d', width, height })
  const img = canvas.createImage()
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve()
    img.onerror = () => reject(new Error('image load failed'))
    img.src = info.path
  })
  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
  ctx.drawImage(img as unknown as CanvasImageSource, 0, 0, width, height)
  const res = await Taro.canvasToTempFilePath({
    canvas: canvas as unknown as Taro.canvasToTempFilePath.Option['canvas'],
    fileType: 'jpg',
    quality: 0.85,
    width,
    height,
    destWidth: width,
    destHeight: height,
  })
  return res.tempFilePath
}
