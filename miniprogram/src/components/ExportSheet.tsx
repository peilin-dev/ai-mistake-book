import { useEffect, useRef, useState } from 'react'
import { View, Text } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { needsSignature } from '../lib/analytics'
import { exportErrorText, exportPdf, loadMe, saveSignature } from '../lib/export'
import type { ExportKind, MeOut } from '../lib/export'
import './components.scss'

export interface ExportItem {
  kind: ExportKind
  label: string
  hint?: string
  submissionId?: number
}

interface Props {
  assignmentId: number
  items: ExportItem[]
  onClose: () => void
}

const NAME_MAX = 32

/** Ask for the signature; null when the teacher cancels or leaves it empty. */
async function askSignature(current: string): Promise<string | null> {
  // Taro's typings omit the editable-input options of wx.showModal.
  const modal = Taro as unknown as {
    showModal: (o: Record<string, unknown>) => Promise<{ confirm: boolean; content?: string }>
  }
  const res = await modal.showModal({
    title: '署名',
    editable: true,
    placeholderText: '例如 王老师',
    content: current,
    confirmText: '保存',
  })
  if (!res.confirm) return null
  const name = (res.content ?? '').trim()
  if (!name) {
    Taro.showToast({ title: '请填写署名', icon: 'none' })
    return null
  }
  if (name.length > NAME_MAX) {
    Taro.showToast({ title: `署名最多 ${NAME_MAX} 个字`, icon: 'none' })
    return null
  }
  return name
}

/** Bottom sheet: pick what to export; the signature is asked for the first time. */
export default function ExportSheet({ assignmentId, items, onClose }: Props) {
  const [me, setMe] = useState<MeOut | null>(null)
  const [busyKind, setBusyKind] = useState<string | null>(null)
  const busy = useRef(false)

  useEffect(() => {
    loadMe()
      .then(setMe)
      .catch(() => {
        // the signature is fetched again on the first tap
      })
  }, [])

  const ensureMe = async (): Promise<MeOut> => me ?? (await loadMe())

  const changeSignature = async () => {
    if (busy.current) return
    busy.current = true
    try {
      const cur = await ensureMe()
      const name = await askSignature(cur.display_name ?? '')
      if (name) setMe(await saveSignature(name))
    } catch (e) {
      Taro.showToast({ title: exportErrorText(e), icon: 'none' })
    } finally {
      busy.current = false
    }
  }

  const run = async (item: ExportItem) => {
    if (busy.current) return
    busy.current = true
    try {
      let cur = await ensureMe()
      if (needsSignature(cur)) {
        const name = await askSignature('')
        if (!name) return
        cur = await saveSignature(name)
      }
      setMe(cur)
      setBusyKind(item.kind)
      await exportPdf(assignmentId, item.kind, item.submissionId)
    } catch (e) {
      const text = exportErrorText(e)
      // Closing the document viewer is not a failure.
      if (!/cancel/i.test((e as { errMsg?: string } | null)?.errMsg ?? '')) {
        Taro.showToast({ title: text, icon: 'none' })
      }
    } finally {
      busy.current = false
      setBusyKind(null)
    }
  }

  return (
    <View className='sheet-mask' onClick={onClose}>
      <View className='sheet' onClick={(e) => e.stopPropagation()}>
        <Text className='sheet-title'>导出 PDF</Text>
        {items.map((it) => (
          <View
            className='card picker-row'
            key={it.kind}
            style={{ opacity: busyKind && busyKind !== it.kind ? 0.5 : 1 }}
            onClick={() => void run(it)}
          >
            <Text style={{ fontSize: '30rpx' }}>{busyKind === it.kind ? '正在生成…' : it.label}</Text>
            {it.hint && busyKind !== it.kind ? <Text className='label picker-no'>{it.hint}</Text> : null}
          </View>
        ))}
        <View style={{ display: 'flex', justifyContent: 'center', padding: '24px 0 8px' }}>
          <Text className='label' style={{ marginBottom: 0 }}>
            署名：{me && !needsSignature(me) ? me.display_name : '未设置'}
          </Text>
          <Text
            className='label'
            style={{ marginBottom: 0, marginLeft: '24px', color: 'var(--link)' }}
            onClick={() => void changeSignature()}
          >
            修改
          </Text>
        </View>
      </View>
    </View>
  )
}
