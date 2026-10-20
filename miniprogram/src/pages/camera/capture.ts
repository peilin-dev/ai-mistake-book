import Taro from '@tarojs/taro'

/** Take one photo with the on-page <Camera>. Resolves to a temp file path. */
export function takePhoto(): Promise<string> {
  const ctx = Taro.createCameraContext()
  return new Promise((resolve, reject) => {
    ctx.takePhoto({
      quality: 'high',
      success: (res) => resolve(res.tempImagePath),
      fail: (err) => reject(err),
    })
  })
}

/** Pick photos from the album, in the order the teacher selected them. Cancel gives []. */
export async function pickFromAlbum(count: number): Promise<string[]> {
  try {
    const res = await Taro.chooseMedia({
      count,
      mediaType: ['image'],
      sourceType: ['album'],
      sizeType: ['compressed'],
    })
    return res.tempFiles.map((f) => f.tempFilePath)
  } catch (e) {
    const msg = (e as { errMsg?: string } | null)?.errMsg ?? ''
    if (msg.includes('cancel')) return []
    throw e
  }
}

export function goBack(): void {
  if (Taro.getCurrentPages().length > 1) void Taro.navigateBack()
  else void Taro.reLaunch({ url: '/pages/index/index' })
}
