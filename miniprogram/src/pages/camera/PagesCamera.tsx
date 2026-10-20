import { useEffect, useRef, useState } from 'react'
import { Button, Text, View } from '@tarojs/components'
import Taro, { useUnload } from '@tarojs/taro'
import { upload } from '../../lib/api'
import { errorText } from '../../lib/messages'
import { compressForUpload } from '../../lib/resize'
import { UploadQueue, type QueueItem } from '../../lib/uploadQueue'
import CameraPane from './CameraPane'
import ThumbStrip from './ThumbStrip'
import { goBack, pickFromAlbum, takePhoto } from './capture'

interface Snap {
  items: QueueItem[]
  paused: { localId: string; message: string } | null
  stopped: null | 'quota'
}

type Uploaded = { page_id: number; seq: number; duplicate: boolean }

/**
 * Student papers: shoot in a row, upload one by one in shooting order in the background.
 * WeChat cannot intercept the system back gesture, so leaving that way just stops the queue
 * (useUnload disposes it); the 完成 button is the one that warns first.
 */
export default function PagesCamera({ assignmentId }: { assignmentId: number }) {
  const queue = useRef<UploadQueue | null>(null)
  if (!queue.current) {
    queue.current = new UploadQueue((p) => upload<Uploaded>(`/api/assignments/${assignmentId}/pages`, p))
  }
  const q = queue.current
  const [snap, setSnap] = useState<Snap>({ items: [], paused: null, stopped: null })
  const [preparing, setPreparing] = useState(0)
  const preparingRef = useRef(0)
  const chain = useRef<Promise<void>>(Promise.resolve())
  const shooting = useRef(false)
  const picking = useRef(false)
  const finishing = useRef(false)

  useEffect(() => {
    const off = q.onChange(() => setSnap({ items: q.items(), paused: q.paused, stopped: q.stopped }))
    return off
  }, [q])
  useUnload(() => q.dispose())

  const bump = (d: number) => {
    preparingRef.current += d
    setPreparing(preparingRef.current)
  }

  /** Compress and enqueue, strictly in the order the photos were taken or selected. */
  const prepare = (paths: string[]) => {
    bump(paths.length)
    chain.current = chain.current.then(async () => {
      for (const p of paths) {
        try {
          q.add(await compressForUpload(p))
        } catch {
          Taro.showToast({ title: '这张照片处理失败，请重拍', icon: 'none' })
        } finally {
          bump(-1)
        }
      }
    })
  }

  const shoot = async () => {
    if (shooting.current) return
    shooting.current = true
    try {
      prepare([await takePhoto()])
    } catch {
      Taro.showToast({ title: '拍照没成功，请再按一次', icon: 'none' })
    } finally {
      shooting.current = false
    }
  }

  const album = async () => {
    if (picking.current) return
    picking.current = true
    try {
      const paths = await pickFromAlbum(20)
      if (paths.length > 0) prepare(paths)
    } catch (e) {
      Taro.showToast({ title: errorText(e), icon: 'none' })
    } finally {
      picking.current = false
    }
  }

  const finish = async () => {
    if (finishing.current) return
    finishing.current = true
    try {
      const n = q.pendingCount() + preparingRef.current
      if (n > 0) {
        const r = await Taro.showModal({
          title: '',
          content: `还有 ${n} 张没传完，离开会中断`,
          confirmText: '继续上传',
          cancelText: '放弃剩余',
        })
        if (r.confirm) return
      }
      q.dispose()
      goBack()
    } finally {
      finishing.current = false
    }
  }

  const done = snap.items.filter((i) => i.state === 'done').length
  const pausedIdx = snap.paused ? snap.items.findIndex((i) => i.localId === snap.paused!.localId) : -1

  const strip = (
    <View>
      {snap.stopped === 'quota' ? (
        <Text style={{ display: 'block', color: '#ffb4ab', padding: '16px 24px 0' }}>
          本月批改额度已用完，后面的照片不会再上传。已传的不受影响。
        </Text>
      ) : null}
      {snap.paused ? (
        <View style={{ background: '#fff', margin: '16px 24px 0', padding: '24px', borderRadius: '16px' }}>
          <Text style={{ display: 'block', color: '#d93025', marginBottom: '16px' }}>
            第 {pausedIdx + 1} 张没传上去：{snap.paused.message}
          </Text>
          <View style={{ display: 'flex' }}>
            <Button className='big-btn' style={{ flex: 1, marginRight: '16px' }} onClick={() => q.retry(snap.paused!.localId)}>
              重试
            </Button>
            <Button className='big-btn ghost-btn' style={{ flex: 1 }} onClick={() => q.skip(snap.paused!.localId)}>
              跳过
            </Button>
          </View>
        </View>
      ) : null}
      <ThumbStrip items={snap.items} pausedId={snap.paused?.localId ?? null} onRetry={(id) => q.retry(id)} />
      <Text style={{ display: 'block', color: '#ccc', fontSize: '26px', padding: '12px 24px 0' }}>
        {snap.items.length === 0
          ? '按快门拍第一张'
          : `已拍 ${snap.items.length + preparing} 张，已传 ${done} 张`}
      </Text>
    </View>
  )

  return (
    <CameraPane
      onShutter={() => void shoot()}
      onAlbum={() => void album()}
      shutterOff={snap.stopped === 'quota'}
      strip={strip}
      right={
        <Text style={{ color: '#07c160', fontSize: '36px', fontWeight: 'bold' }} onClick={() => void finish()}>
          完成
        </Text>
      }
    />
  )
}
