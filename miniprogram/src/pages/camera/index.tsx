import { Button, Text, View } from '@tarojs/components'
import { useRouter } from '@tarojs/taro'
import PagesCamera from './PagesCamera'
import SingleShot from './SingleShot'
import { goBack } from './capture'

export default function CameraPage() {
  const params = useRouter().params
  const assignmentId = Number(params.assignmentId)
  const pageId = Number(params.pageId)
  const mode = params.mode
  const okId = Number.isInteger(assignmentId) && assignmentId > 0

  if (okId && mode === 'pages') return <PagesCamera assignmentId={assignmentId} />
  if (okId && mode === 'answerKey') return <SingleShot mode='answerKey' assignmentId={assignmentId} />
  if (okId && mode === 'replace' && Number.isInteger(pageId) && pageId > 0) {
    return <SingleShot mode='replace' assignmentId={assignmentId} pageId={pageId} />
  }
  return (
    <View className='page'>
      <Text className='label'>打不开拍照页，请返回重试</Text>
      <Button className='big-btn' onClick={goBack}>
        返回
      </Button>
    </View>
  )
}
