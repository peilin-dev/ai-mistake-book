import { useState, type ReactNode } from 'react'
import { Camera, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'

interface Props {
  onShutter: () => void
  onAlbum: () => void
  /** Greys out the shutter (e.g. the monthly quota is used up). */
  shutterOff?: boolean
  /** Shown above the controls: thumbnails, paused-upload banner, … */
  strip?: ReactNode
  /** Right-hand control, e.g. the "完成" button. */
  right?: ReactNode
}

/** Full-screen viewfinder with a shutter row below it. Handles a denied camera permission. */
export default function CameraPane({ onShutter, onAlbum, shutterOff, strip, right }: Props) {
  const [denied, setDenied] = useState(false)
  const [cameraKey, setCameraKey] = useState(0)

  const openSettings = async () => {
    try {
      await Taro.openSetting()
    } catch {
      // closed without changes
    }
    setDenied(false)
    setCameraKey((k) => k + 1) // remount the camera to pick up a new permission
  }

  return (
    <View style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#000' }}>
      <View style={{ flex: 1, position: 'relative' }}>
        {denied ? (
          <View style={{ padding: '96px 48px', textAlign: 'center' }}>
            <Text style={{ color: '#fff', fontSize: '34px', display: 'block', marginBottom: '48px' }}>
              没有拿到相机权限。可以去设置里打开相机，或者直接从相册选照片。
            </Text>
            <View
              style={{ background: '#07c160', color: '#fff', borderRadius: '16px', lineHeight: '100px' }}
              onClick={() => void openSettings()}
            >
              去设置
            </View>
          </View>
        ) : (
          <Camera
            key={cameraKey}
            devicePosition='back'
            flash='off'
            style={{ width: '100%', height: '100%' }}
            onError={() => setDenied(true)}
          />
        )}
      </View>
      <View style={{ background: '#111', paddingBottom: '24px' }}>
        {strip}
        <View
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 48px 0',
          }}
        >
          <View style={{ width: '200px' }} onClick={onAlbum}>
            <Text style={{ color: '#fff', fontSize: '32px' }}>从相册选</Text>
          </View>
          <View
            onClick={denied || shutterOff ? undefined : onShutter}
            style={{
              width: '128px',
              height: '128px',
              borderRadius: '64px',
              background: denied || shutterOff ? '#555' : '#fff',
              border: '8px solid #888',
              boxSizing: 'border-box',
            }}
          />
          <View style={{ width: '200px', textAlign: 'right' }}>{right}</View>
        </View>
      </View>
    </View>
  )
}
