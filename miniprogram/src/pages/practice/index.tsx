import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter, useUnload } from '@tarojs/taro'
import { ApiError, request } from '../../lib/api'
import { errorText } from '../../lib/messages'
import {
  FAILED_TEXT,
  PARTIAL_TEXT,
  REPLACE_FAILED_TEXT,
  failedReplace,
  generatedAtText,
  isWorking,
  optionLetter,
  progressText,
  sourceLabel,
} from '../../lib/practice'
import ExportSheet from '../../components/ExportSheet'
import type { PracticePaperOut, SubmissionOut } from '../../lib/types'

type Phase = 'loading' | 'ok' | 'blocked' | 'error' | 'notfound'

const POLL_MS = 2000

/** 409 carries a readable reason from the server; everything else uses the shared texts. */
function msg(e: unknown): string {
  if (e instanceof ApiError && e.status === 409 && e.detail) return e.detail
  return errorText(e)
}

export default function PracticePage() {
  const params = useRouter().params
  const assignmentId = Number(params.assignmentId)
  const submissionId = Number(params.submissionId)
  const byStudent = Number.isInteger(submissionId) && submissionId > 0
  const validId = byStudent || (Number.isInteger(assignmentId) && assignmentId > 0)
  const latestUrl = byStudent
    ? `/api/submissions/${submissionId}/practice`
    : `/api/assignments/${assignmentId}/practice`

  const [phase, setPhase] = useState<Phase>(validId ? 'loading' : 'notfound')
  const [blockedText, setBlockedText] = useState('')
  const [paper, setPaper] = useState<PracticePaperOut | null>(null)
  const [opened, setOpened] = useState<number[]>([])
  const [failedItem, setFailedItem] = useState<number | null>(null)
  const [exporting, setExporting] = useState(false)
  const [exportAssignment, setExportAssignment] = useState<number | null>(byStudent ? null : assignmentId)

  const seq = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const shown = useRef(false)
  const paperRef = useRef<PracticePaperOut | null>(null)
  const asked = useRef<number[]>([])
  const regenerating = useRef(false)
  const replaceBusy = useRef(new Set<number>())

  const stopPoll = () => {
    if (timer.current !== null) clearTimeout(timer.current)
    timer.current = null
  }

  const apply = (p: PracticePaperOut) => {
    paperRef.current = p
    setPaper(p)
    setPhase('ok')
    const failed = failedReplace(asked.current, p)
    if (failed !== null) {
      setFailedItem(failed)
      Taro.showToast({ title: REPLACE_FAILED_TEXT, icon: 'none' })
    }
    // an item that is no longer replacing is settled either way
    asked.current = asked.current.filter((id) => p.items.some((i) => i.id === id && i.replacing))
    stopPoll()
    if (isWorking(p) && shown.current) {
      timer.current = setTimeout(() => void poll(p.id), POLL_MS)
    }
  }

  const poll = async (id: number) => {
    const mine = ++seq.current
    try {
      const p = await request<PracticePaperOut>('GET', `/api/practice/${id}`)
      if (mine !== seq.current) return
      apply(p)
    } catch (e) {
      if (mine !== seq.current) return
      if (e instanceof ApiError && e.status === 404) {
        setPhase('notfound')
        return
      }
      // a failed poll is retried quietly while the page is visible
      stopPoll()
      if (shown.current) timer.current = setTimeout(() => void poll(id), POLL_MS)
    }
  }

  const resolveExportAssignment = async (): Promise<number | null> => {
    if (exportAssignment !== null) return exportAssignment
    try {
      const s = await request<SubmissionOut>('GET', `/api/submissions/${submissionId}`)
      const aid = s.assignment_id ?? null
      setExportAssignment(aid)
      return aid
    } catch (e) {
      Taro.showToast({ title: errorText(e), icon: 'none' })
      return null
    }
  }

  /** Open the page: show the latest paper, or start one when there is none yet. */
  const initial = async () => {
    if (!validId) return
    const mine = ++seq.current
    try {
      let p: PracticePaperOut
      try {
        p = await request<PracticePaperOut>('GET', latestUrl)
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) throw e
        p = await request<PracticePaperOut>('POST', latestUrl)
      }
      if (mine !== seq.current) return
      apply(p)
    } catch (e) {
      if (mine !== seq.current) return
      if (e instanceof ApiError && e.status === 404) {
        setPhase('notfound')
      } else if (e instanceof ApiError && e.status === 409 && e.detail) {
        setBlockedText(e.detail)
        setPhase('blocked')
      } else {
        Taro.showToast({ title: errorText(e), icon: 'none' })
        setPhase('error')
      }
    }
  }

  useDidShow(() => {
    shown.current = true
    if (paperRef.current) void poll(paperRef.current.id)
    else void initial()
  })
  const pause = () => {
    shown.current = false
    stopPoll()
    seq.current += 1 // drop any in-flight response
  }
  useDidHide(pause)
  useUnload(pause)

  const retryLoad = () => {
    setPhase('loading')
    void initial()
  }
  const back = () => {
    if (Taro.getCurrentPages().length > 1) void Taro.navigateBack()
    else void Taro.reLaunch({ url: '/pages/index/index' })
  }

  const doRegenerate = async () => {
    if (regenerating.current) return
    regenerating.current = true
    try {
      const mine = ++seq.current
      const p = await request<PracticePaperOut>('POST', latestUrl)
      if (mine !== seq.current) return
      asked.current = []
      setFailedItem(null)
      setOpened([])
      apply(p)
    } catch (e) {
      Taro.showToast({ title: msg(e), icon: 'none' })
    } finally {
      regenerating.current = false
    }
  }

  const regenerate = async () => {
    if (paper && paper.status === 'done') {
      const res = await Taro.showModal({
        title: '重新生成',
        content: '会换掉现在这张练习纸上的全部题目，确定吗？',
        confirmText: '重新生成',
      })
      if (!res.confirm) return
    }
    await doRegenerate()
  }

  const replaceItem = async (itemId: number) => {
    if (replaceBusy.current.has(itemId)) return
    replaceBusy.current.add(itemId)
    try {
      setFailedItem(null)
      await request('POST', `/api/practice-items/${itemId}/replace`)
      setOpened((o) => o.filter((x) => x !== itemId)) // the new question's answer starts folded
      asked.current = [...asked.current, itemId]
      const cur = paperRef.current
      if (cur) {
        const next = { ...cur, items: cur.items.map((i) => (i.id === itemId ? { ...i, replacing: true } : i)) }
        apply(next)
        void poll(cur.id)
      }
    } catch (e) {
      Taro.showToast({ title: msg(e), icon: 'none' })
    } finally {
      replaceBusy.current.delete(itemId)
    }
  }

  const toggleAnswer = (id: number) => {
    setOpened((o) => (o.includes(id) ? o.filter((x) => x !== id) : [...o, id]))
  }

  const openExport = async () => {
    if ((await resolveExportAssignment()) !== null) setExporting(true)
  }

  if (phase === 'loading') {
    return (
      <View className='page'>
        <Text className='label'>加载中…</Text>
      </View>
    )
  }
  if (phase === 'notfound') {
    return (
      <View className='page'>
        <Text className='label'>找不到这份练习</Text>
        <Button className='big-btn' onClick={back}>
          返回
        </Button>
      </View>
    )
  }
  if (phase === 'blocked') {
    return (
      <View className='page'>
        <View className='card'>
          <Text style={{ display: 'block' }}>{blockedText}</Text>
        </View>
        <Button className='big-btn' onClick={back}>
          返回
        </Button>
      </View>
    )
  }
  if (phase === 'error' || !paper) {
    return (
      <View className='page'>
        <Text className='label'>加载失败，请检查网络后重试</Text>
        <Button className='big-btn' onClick={retryLoad}>
          重新加载
        </Button>
        <Button className='big-btn ghost-btn' style={{ marginTop: '32rpx' }} onClick={back}>
          返回
        </Button>
      </View>
    )
  }

  const working = paper.status === 'queued' || paper.status === 'running'
  if (working) {
    const total = Math.max(paper.sources_total, 1)
    return (
      <View className='page'>
        <View className='card card-band band-busy'>
          <Text className='strong' style={{ display: 'block' }}>{progressText(paper)}</Text>
          <View className='progress'>
            <View
              className='progress-fill fill-busy'
              style={{ width: `${Math.round((paper.sources_done / total) * 100)}%` }}
            />
          </View>
          <Text className='label' style={{ marginTop: '20rpx', marginBottom: 0 }}>
            一般不到一分钟，可以留在这里等
          </Text>
        </View>
      </View>
    )
  }
  if (paper.status === 'failed' || paper.items.length === 0) {
    return (
      <View className='page'>
        <View className='card card-band band-danger'>
          <Text style={{ display: 'block' }}>{FAILED_TEXT}</Text>
        </View>
        <Button className='big-btn' onClick={() => void doRegenerate()}>
          重新生成
        </Button>
      </View>
    )
  }

  const when = generatedAtText(paper.generated_at)
  return (
    <View className='page'>
      <Text className='title-lg' style={{ display: 'block', margin: '8rpx 0 8rpx' }}>
        {paper.scope === 'student' && paper.student_name ? `${paper.student_name}的同类题练习` : '全班同类题练习'}
      </Text>
      <Text className='label'>
        共 {paper.items.length} 道题，答案已由第二个模型独立验算
      </Text>
      {when ? <Text className='label'>生成于 {when}</Text> : null}
      {paper.partial ? (
        <Text className='label hint'>{PARTIAL_TEXT}</Text>
      ) : null}

      {paper.items.map((it, idx) => {
        const open = opened.includes(it.id)
        return (
          <View className='card card-band band-warn' key={it.id}>
            <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text className='strong'>第 {idx + 1} 题</Text>
              <Text className='label' style={{ marginBottom: 0 }}>{sourceLabel(it)}</Text>
            </View>
            <Text style={{ display: 'block', marginTop: '16rpx' }}>{it.stem}</Text>
            {it.options && it.options.length > 0
              ? it.options.map((o, i) => (
                  <Text key={i} style={{ display: 'block', marginTop: '8rpx', color: 'var(--ink-2)' }}>
                    {optionLetter(i)}. {o}
                  </Text>
                ))
              : null}
            {open ? (
              <Text className='text-ok' style={{ display: 'block', marginTop: '16rpx' }}>答案：{it.answer}</Text>
            ) : null}
            {failedItem === it.id && !it.replacing ? (
              <Text className='label hint' style={{ marginTop: '12rpx', marginBottom: 0 }}>{REPLACE_FAILED_TEXT}</Text>
            ) : null}
            <View style={{ display: 'flex', justifyContent: 'space-between', marginTop: '20rpx' }}>
              <Text className='link' onClick={() => toggleAnswer(it.id)}>{open ? '收起答案' : '看答案'}</Text>
              {it.replacing ? (
                <Text className='muted'>正在换…</Text>
              ) : (
                <Text className='link' onClick={() => void replaceItem(it.id)}>换一道</Text>
              )}
            </View>
          </View>
        )
      })}

      <View className='bottom-bar' style={{ display: 'flex' }}>
        <Button
          className='big-btn ghost-btn'
          style={{ flex: 1, width: 'auto', marginRight: '16rpx' }}
          onClick={() => void regenerate()}
        >
          重新生成
        </Button>
        <Button className='big-btn' style={{ flex: 1, width: 'auto' }} onClick={() => void openExport()}>
          导出 PDF
        </Button>
      </View>
      {exporting && exportAssignment !== null ? (
        <ExportSheet
          assignmentId={exportAssignment}
          answersSwitch
          items={[
            byStudent
              ? { kind: 'practice_student', label: '这份练习纸', hint: paper.student_name ?? undefined, submissionId }
              : { kind: 'practice', label: '全班练习纸' },
          ]}
          onClose={() => setExporting(false)}
        />
      ) : null}
    </View>
  )
}
