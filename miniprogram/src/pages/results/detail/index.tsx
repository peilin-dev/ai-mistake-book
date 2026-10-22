import { useRef, useState } from 'react'
import { View, Text, Button, Image } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { ApiError, request } from '../../../lib/api'
import { errorText } from '../../../lib/messages'
import { NO_ANSWER_KEY_BANNER, scoreText, verdictText } from '../../../lib/results'
import type { AssignmentOut, SubmissionOut } from '../../../lib/types'

type LoadState = 'loading' | 'ok' | 'error' | 'notfound'

export default function ResultDetail() {
  const submissionId = Number(useRouter().params.submissionId)
  const validId = Number.isInteger(submissionId) && submissionId > 0
  const [state, setState] = useState<LoadState>(validId ? 'loading' : 'notfound')
  const [sub, setSub] = useState<SubmissionOut | null>(null)
  const [hasKey, setHasKey] = useState(true)
  const seq = useRef(0)
  const loaded = useRef(false)
  const triedRefresh = useRef(new Set<number>())

  const fetchSub = () => request<SubmissionOut>('GET', `/api/submissions/${submissionId}`)

  const load = async () => {
    if (!validId) return
    const mine = ++seq.current
    try {
      const s = await fetchSub()
      const a = await request<AssignmentOut>('GET', `/api/assignments/${s.assignment_id}`)
      if (mine !== seq.current) return
      setSub(s)
      setHasKey(a.has_answer_key)
      triedRefresh.current.clear()
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

  /** Signed crop URLs expire: refetch the submission once per question, then give up. */
  const onCropError = async (questionId: number) => {
    if (triedRefresh.current.has(questionId)) return
    triedRefresh.current.add(questionId)
    try {
      const fresh = await fetchSub()
      setSub(fresh)
    } catch {
      // leave the broken image; nothing useful to tell the teacher
    }
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
        <Text className='label'>找不到这位同学的成绩</Text>
        <Button className='big-btn' onClick={back}>
          返回
        </Button>
      </View>
    )
  }
  if (state === 'error' || !sub) {
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

  const questions = sub.questions ?? []
  return (
    <View className='page'>
      {!hasKey ? (
        <Text className='label' style={{ color: 'var(--warn-text)' }}>
          {NO_ANSWER_KEY_BANNER}
        </Text>
      ) : null}
      <View className='card'>
        <Text className='title-xl' style={{ display: 'block' }}>{sub.student_name}</Text>
        <Text style={{ fontSize: '34px', display: 'block', marginTop: '8px' }}>总分 {sub.total_score} 分</Text>
        {sub.needs_review_count > 0 ? (
          <Text className='pill pill-warn' style={{ marginTop: '12px' }}>
            待复核 {sub.needs_review_count}
          </Text>
        ) : null}
      </View>
      {questions.map((q) => (
        <View className={`card card-band ${q.is_correct ? 'band-ok' : 'band-danger'}`} key={q.id}>
          <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text className='strong'>第 {q.question_no} 题</Text>
            <View style={{ display: 'flex', alignItems: 'center' }}>
              {!q.answer_verified ? (
                <Text className='pill pill-busy' style={{ marginRight: '12px' }}>
                  AI 判断
                </Text>
              ) : null}
              <Text className={`strong ${q.is_correct ? 'text-ok' : 'text-danger'}`}>
                {verdictText(q)}　{scoreText(q)}
              </Text>
            </View>
          </View>
          {q.crop_url ? (
            <Image
              src={q.crop_url}
              mode='widthFix'
              style={{ width: '100%', marginTop: '16px' }}
              onError={() => void onCropError(q.id)}
              onClick={() => void Taro.previewImage({ urls: [q.crop_url as string] })}
            />
          ) : null}
          <Text className='label' style={{ marginTop: '16px' }}>学生答案</Text>
          <Text style={{ display: 'block' }}>{q.student_answer ?? '（没看清）'}</Text>
          <Text className='label' style={{ marginTop: '16px' }}>正确答案</Text>
          <Text style={{ display: 'block' }}>{q.correct_answer ?? '（无）'}</Text>
        </View>
      ))}
    </View>
  )
}
