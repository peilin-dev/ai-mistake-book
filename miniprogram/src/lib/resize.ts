import Taro from '@tarojs/taro'

/** Scale so the long edge is at most maxLong; never enlarge. */
export function targetSize(w: number, h: number, maxLong = 2000): { width: number; height: number } {
  const long = Math.max(w, h)
  if (long <= maxLong) return { width: Math.round(w), height: Math.round(h) }
  const k = maxLong / long
  return { width: Math.max(1, Math.round(w * k)), height: Math.max(1, Math.round(h * k)) }
}

/**
 * Page-side only: shrink the photo to targetSize and re-encode as JPEG
 * quality 85 with wx.compressImage (base library >= 2.26.0 for
 * compressedWidth/Height). An image that already fits is only re-encoded.
 * Returns a temp file path.
 */
export async function compressForUpload(path: string): Promise<string> {
  const info = await Taro.getImageInfo({ src: path })
  const { width, height } = targetSize(info.width, info.height)
  const resized = width !== info.width || height !== info.height
  const res = await Taro.compressImage({
    src: path,
    quality: 85,
    ...(resized ? { compressedWidth: width, compressedHeight: height } : {}),
  })
  return res.tempFilePath
}
