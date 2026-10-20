import { useRef, useState } from 'react'
import { Button, Input, Text, View } from '@tarojs/components'
import Taro, { useLoad, useRouter } from '@tarojs/taro'
import { ApiError, request } from '../../lib/api'
import { blankRow, toPutBody, toRows, validateRows, type KeyRow } from '../../lib/answerKey'
import { errorText } from '../../lib/messages'
import type { AnswerKeyItem } from '../../lib/types'

type LoadState = 'loading' | 'ok' | 'error' | 'notfound'

interface KeyOut {
  answer_key_status: string
  items: AnswerKeyItem[]
}
interface ConfirmOut extends KeyOut {
  regrade_suggested: boolean
}

function back() {
  if (Taro.getCurrentPages().length > 1) void Taro.navigateBack()
  else void Taro.reLaunch({ url: '/pages/index/index' })
}

export default function AnswerKeyPage() {
  const assignmentId = Number(useRouter().params.assignmentId)
  const validId = Number.isInteger(assignmentId) && assignmentId > 0
  const [state, setState] = useState<LoadState>(validId ? 'loading' : 'notfound')
  const [rows, setRows] = useState<KeyRow[]>([])
  const [saving, setSaving] = useState(false)
  const saveGuard = useRef(false)

  const load = async () => {
    setState('loading')
    try {
      const out = await request<KeyOut>('GET', `/api/assignments/${assignmentId}/answer-key`)
      setRows(toRows(out.items))
      setState('ok')
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setState('notfound')
      } else {
        Taro.showToast({ title: errorText(e), icon: 'none' })
        setState('error')
      }
    }
  }
  useLoad(() => {
    if (validId) void load()
  })

  const edit = (key: string, patch: Partial<KeyRow>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  const remove = (key: string) => setRows((rs) => rs.filter((r) => r.key !== key))

  const confirm = async () => {
    if (saveGuard.current) return
    const problem = validateRows(rows)
    if (problem) {
      Taro.showToast({ title: problem, icon: 'none', duration: 3000 })
      return
    }
    saveGuard.current = true
    setSaving(true)
    try {
      const out = await request<ConfirmOut>('PUT', `/api/assignments/${assignmentId}/answer-key`, toPutBody(rows))
      if (out.regrade_suggested) {
        await Taro.showModal({ title: '', content: '已批的卷子不会自动重批', showCancel: false, confirmText: '知道了' })
      }
      back()
    } catch (e) {
      Taro.showToast({ title: errorText(e), icon: 'none', duration: 3000 })
      saveGuard.current = false
      setSaving(false)
    }
  }

  const reshoot = () => {
    void Taro.redirectTo({ url: `/pages/camera/index?mode=answerKey&assignmentId=${assignmentId}` })
  }

  if (state === 'loading') {
    return (
      <View className='page'>
        <Text className='label'>加载中…</Text>
      </View>
    )
  }
  if (state === 'notfound') {
    return (
      <View className='page'>
        <Text className='label'>找不到这份作业</Text>
        <Button className='big-btn' onClick={back}>
          返回
        </Button>
      </View>
    )
  }
  if (state === 'error') {
    return (
      <View className='page'>
        <Text className='label'>加载失败，请检查网络后重试</Text>
        <Button className='big-btn' onClick={() => void load()}>
          重新加载
        </Button>
      </View>
    )
  }

  return (
    <View className='page' style={{ paddingBottom: '260px' }}>
      <Text className='label'>请核对 AI 识别的答案，可以直接修改。分值可以不填。</Text>
      {rows.length === 0 ? (
        <View className='card'>
          <Text style={{ display: 'block', marginBottom: '24px' }}>没有识别出题目，可以重新拍一张，或者手动加题。</Text>
          <Button className='big-btn ghost-btn' onClick={reshoot}>
            重新拍答案卷
          </Button>
        </View>
      ) : null}
      {rows.map((r, i) => (
        <View className='card' key={r.key}>
          <View style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
            <Text style={{ fontWeight: 'bold' }}>第 {i + 1} 行</Text>
            <Text style={{ color: '#d93025' }} onClick={() => remove(r.key)}>
              删除
            </Text>
          </View>
          <Text className='label'>题号</Text>
          <Input
            className='field'
            value={r.question_no}
            placeholder='例如 1'
            onInput={(e) => edit(r.key, { question_no: e.detail.value })}
          />
          <Text className='label'>答案</Text>
          <Input
            className='field'
            value={r.answer}
            placeholder='标准答案'
            onInput={(e) => edit(r.key, { answer: e.detail.value })}
          />
          <Text className='label'>分值（可不填）</Text>
          <Input
            className='field'
            type='digit'
            value={r.max_score}
            placeholder='例如 2'
            onInput={(e) => edit(r.key, { max_score: e.detail.value })}
          />
        </View>
      ))}
      <Button className='big-btn ghost-btn' onClick={() => setRows((rs) => [...rs, blankRow()])}>
        加一题
      </Button>
      <View className='bottom-bar'>
        <Button className='big-btn' disabled={saving} onClick={() => void confirm()}>
          确认答案
        </Button>
      </View>
    </View>
  )
}
