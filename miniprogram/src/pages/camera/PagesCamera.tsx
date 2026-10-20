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

const PREPARE_FAILED_TEXT = '这张照片处理失败，请重拍这张'

/**
 * Student papers: shoot in a row, upload one by one in shooting order in the background.
 * WeChat cannot intercept the system back gesture, so leaving that way just stops the queue
 * (useUnload disposes it); the 完成 button is the one that warns first.
 *
 * Upload order must equal shooting order (the backend links a nameless page to the page
 * uploaded just before it), so a photo that did not go up is never skipped: the teacher
 * retries it or re-shoots it in place (重拍这张).
 */
export default function PagesCamera({ assignmentId }: { assignmentId: number }) {
  const queue = useRef<UploadQueue | null>(null)
  if (!queue.current) {
    queue.current = new UploadQueue((p) => upload<Uploaded>(`/api/assignments/${assignmentId}/pages`, p))
  }
  const q = queue.current
  const [snap, setSnap] = useState<Snap>({ items: [], paused: null, stopped: null })
  const [preparing, setPreparing] = useState(0)
  /** localId of the paused item the next shutter / album photo will replace. */
  const [retakeFor, setRetakeFor] = useState<string | null>(null)
  const preparingRef = useRef(0)
  const chain = useRef<Promise<void>>(Promise.resolve())
  const disposed = useRef(false)
  const shooting = useRef(false)
  const picking = useRef(false)
  const finishing = useRef(false)

  useEffect(() => {
    const off = q.onChange(() => setSnap({ items: q.items(), paused: q.paused, stopped: q.stopped }))
    return off
  }, [q])
  useUnload(() => {
    disposed.current = true
    q.dispose()
  })

  // Leave retake mode once that item is no longer the paused one.
  useEffect(() => {
    if (retakeFor !== null && snap.paused?.localId !== retakeFor) setRetakeFor(null)
  }, [snap.paused, retakeFor])

  const bump = (d: number) => {
    preparingRef.current += d
    setPreparing(preparingRef.current)
  }

  /** Compress and enqueue, strictly in the order the photos were taken or selected. */
  const prepare = (paths: string[]) => {
    bump(paths.length)
    chain.current = chain.current.then(async () => {
      for (const p of paths) {
        if (disposed.current) return
        try {
          const out = await compressForUpload(p)
          if (disposed.current) return
          q.add(out)
        } catch {
          if (disposed.current) return
          // Keep its place in line so nothing behind it uploads before it is re-shot.
          q.addFailed(PREPARE_FAILED_TEXT)
        } finally {
          bump(-1)
        }
      }
    })
  }

  /** 重拍这张: the new photo takes the paused item's place in the queue. */
  const replace = async (localId: string, path: string) => {
    try {
      const out = await compressForUpload(path)
      if (disposed.current) return
      q.replaceFile(localId, out)
    } catch {
      // Still paused on the same item and still in retake mode: just shoot again.
      Taro.showToast({ title: '这张照片处理失败，请再拍一次', icon: 'none' })
    }
  }

  const shoot = async () => {
    if (shooting.current) return
    shooting.current = true
    try {
      const path = await takePhoto()
      if (retakeFor !== null) await replace(retakeFor, path)
      else prepare([path])
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
      if (retakeFor !== null) {
        const [path] = await pickFromAlbum(1)
        if (path) await replace(retakeFor, path)
      } else {
        const paths = await pickFromAlbum(20)
        if (paths.length > 0) prepare(paths)
      }
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
      disposed.current = true
      q.dispose()
      goBack()
    } finally {
      finishing.current = false
    }
  }

  const done = snap.items.filter((i) => i.state === 'done').length
  const pausedIdx = snap.paused ? snap.items.findIndex((i) => i.localId === snap.paused!.localId) : -1
  const pausedItem = pausedIdx >= 0 ? snap.items[pausedIdx] : null

  const pausedCard = snap.paused ? (
    <View style={{ background: '#fff', margin: '16px 24px 0', padding: '24px', borderRadius: '16px' }}>
      {retakeFor !== null ? (
        <View>
          <Text style={{ display: 'block', color: '#333', marginBottom: '16px' }}>
            对准第 {pausedIdx + 1} 张按快门重拍，也可以从相册选一张。后面的照片会接着传。
          </Text>
          <Button className='big-btn ghost-btn' onClick={() => setRetakeFor(null)}>
            取消重拍
          </Button>
        </View>
      ) : (
        <View>
          <Text style={{ display: 'block', color: '#d93025', marginBottom: '16px' }}>
            第 {pausedIdx + 1} 张没传上去：{snap.paused.message}。后面的照片先等它传完。
          </Text>
          <View style={{ display: 'flex' }}>
            {pausedItem?.retakeOnly ? null : (
              <Button className='big-btn' style={{ flex: 1, marginRight: '16px' }} onClick={() => q.retry(snap.paused!.localId)}>
                重试
              </Button>
            )}
            <Button
              className={pausedItem?.retakeOnly ? 'big-btn' : 'big-btn ghost-btn'}
              style={{ flex: 1 }}
              onClick={() => setRetakeFor(snap.paused!.localId)}
            >
              重拍这张
            </Button>
          </View>
        </View>
      )}
    </View>
  ) : null

  const strip = (
    <View>
      {snap.stopped === 'quota' ? (
        <Text style={{ display: 'block', color: '#ffb4ab', padding: '16px 24px 0' }}>
          本月批改额度已用完，后面的照片不会再上传。已传的不受影响。
        </Text>
      ) : null}
      {pausedCard}
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
