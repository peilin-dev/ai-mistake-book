import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { ApiError, request } from '../../lib/api'
import { errorText } from '../../lib/messages'
import { NO_ANSWER_KEY_BANNER } from '../../lib/results'
import type { AssignmentOut, SubmissionOut } from '../../lib/types'

type LoadState = 'loading' | 'ok' | 'error' | 'notfound'

export default function Results() {
  const assignmentId = Number(useRouter().params.assignmentId)
  const validId = Number.isInteger(assignmentId) && assignmentId > 0
  const [state, setState] = useState<LoadState>(validId ? 'loading' : 'notfound')
  const [assignment, setAssignment] = useState<AssignmentOut | null>(null)
  const [subs, setSubs] = useState<SubmissionOut[]>([])
  const seq = useRef(0)
  const loaded = useRef(false)

  const load = async () => {
    if (!validId) return
    const mine = ++seq.current
    try {
      const [a, list] = await Promise.all([
        request<AssignmentOut>('GET', `/api/assignments/${assignmentId}`),
        request<SubmissionOut[]>('GET', `/api/assignments/${assignmentId}/submissions`),
      ])
      if (mine !== seq.current) return
      setAssignment(a)
      setSubs(list)
      loaded.current = true
      setState('ok')
    } catch (e) {
      if (mine !== seq.current) return
      if (e instanceof ApiError && e.status === 404) {
        setState('notfound')
      } else {
        Taro.showToast({ title: errorText(e), icon: 'none' })
        if (!loaded.current) setState('error')
      }
    }
  }

  // Runs again when coming back from the detail page, so scores are fresh.
  useDidShow(() => {
    void load()
  })

  const retryLoad = () => {
    setState('loading')
    void load()
  }
  const back = () => {
    if (Taro.getCurrentPages().length > 1) void Taro.navigateBack()
    else void Taro.reLaunch({ url: '/pages/index/index' })
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
  if (state === 'error' || !assignment) {
    return (
      <View className='page'>
        <Text className='label'>加载失败，请检查网络后重试</Text>
        <Button className='big-btn' onClick={retryLoad}>
          重新加载
        </Button>
        <Button className='big-btn ghost-btn' style={{ marginTop: '16px' }} onClick={back}>
          返回
        </Button>
      </View>
    )
  }

  return (
    <View className='page'>
      {!assignment.has_answer_key ? (
        <Text className='label' style={{ color: '#8a6100' }}>
          {NO_ANSWER_KEY_BANNER}
        </Text>
      ) : null}
      {subs.length === 0 ? (
        <Text className='label'>还没有出成绩的学生</Text>
      ) : (
        subs.map((s) => (
          <View
            className='card'
            key={s.id}
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
            onClick={() => void Taro.navigateTo({ url: `/pages/results/detail/index?submissionId=${s.id}` })}
          >
            <Text style={{ fontSize: '34px', fontWeight: 'bold' }}>{s.student_name}</Text>
            <View style={{ display: 'flex', alignItems: 'center' }}>
              {s.needs_review_count > 0 ? (
                <Text className='pill pill-warn' style={{ marginRight: '16px' }}>
                  待复核 {s.needs_review_count}
                </Text>
              ) : null}
              <Text style={{ fontSize: '40px', fontWeight: 'bold' }}>{s.total_score} 分</Text>
            </View>
          </View>
        ))
      )}
    </View>
  )
}
