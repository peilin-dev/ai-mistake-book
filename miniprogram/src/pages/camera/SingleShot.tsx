import { useRef, useState } from 'react'
import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { upload } from '../../lib/api'
import { errorText } from '../../lib/messages'
import { compressForUpload } from '../../lib/resize'
import CameraPane from './CameraPane'
import { goBack, pickFromAlbum, takePhoto } from './capture'

interface Props {
  mode: 'answerKey' | 'replace'
  assignmentId: number
  pageId?: number
}

/** One photo for the answer key (then P6) or to replace a failed page (then back to P4). */
export default function SingleShot({ mode, assignmentId, pageId }: Props) {
  const [working, setWorking] = useState(false)
  const busy = useRef(false)

  const send = async (file: string) => {
    if (mode === 'answerKey') {
      await upload(`/api/assignments/${assignmentId}/answer-key`, file)
      await Taro.redirectTo({ url: `/pages/answer-key/index?assignmentId=${assignmentId}` })
    } else {
      await upload(`/api/pages/${pageId}:replace`, file)
      Taro.showToast({ title: '已重新提交', icon: 'success' })
      goBack()
    }
  }

  const run = async (getPath: () => Promise<string | null>) => {
    if (busy.current) return
    busy.current = true
    let leaving = false // after a successful upload the page is going away: stay locked
    try {
      let path: string | null
      try {
        path = await getPath()
      } catch {
        Taro.showToast({ title: '拍照没成功，请再按一次', icon: 'none' })
        return
      }
      if (!path) return
      setWorking(true)
      let file: string
      try {
        file = await compressForUpload(path)
      } catch {
        Taro.showToast({ title: '这张照片处理失败，请重拍', icon: 'none' })
        setWorking(false)
        return
      }
      try {
        await send(file)
        leaving = true
      } catch (e) {
        Taro.showToast({ title: errorText(e), icon: 'none', duration: 3000 })
        setWorking(false)
      }
    } finally {
      if (!leaving) busy.current = false
    }
  }

  if (working) {
    return (
      <View style={{ padding: '240px 48px 0', textAlign: 'center' }}>
        <Text className='title-xl' style={{ display: 'block', marginBottom: '16px' }}>
          {mode === 'answerKey' ? '正在识别答案…' : '正在上传…'}
        </Text>
        {mode === 'answerKey' ? <Text className='label'>大约需要 10 到 30 秒，请不要离开</Text> : null}
      </View>
    )
  }

  return (
    <CameraPane
      onShutter={() => void run(takePhoto)}
      onAlbum={() => void run(async () => (await pickFromAlbum(1))[0] ?? null)}
    />
  )
}
