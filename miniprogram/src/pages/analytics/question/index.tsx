import { useRef, useState } from 'react'
import { View, Text, Button, Image } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { ApiError, request } from '../../../lib/api'
import { AI_LABEL } from '../../../lib/analytics'
import { errorText } from '../../../lib/messages'
import type { CausesOut, QuestionDetailOut } from '../../../lib/types'

type LoadState = 'loading' | 'ok' | 'error' | 'notfound'

export default function QuestionDetailPage() {
  const params = useRouter().params
  const assignmentId = Number(params.assignmentId)
  const no = params.no ? decodeURIComponent(String(params.no)) : ''
  const validId = Number.isInteger(assignmentId) && assignmentId > 0 && no !== ''
  const [state, setState] = useState<LoadState>(validId ? 'loading' : 'notfound')
  const [detail, setDetail] = useState<QuestionDetailOut | null>(null)
  const [causes, setCauses] = useState<Record<string, string>>({})
  const seq = useRef(0)
  const loaded = useRef(false)
  const causesAsked = useRef(false)
  const triedRefresh = useRef(false)

  const base = `/api/assignments/${assignmentId}/analytics/questions/${encodeURIComponent(no)}`

  /** AI causes arrive after the page is already readable; failure just means no causes. */
  const loadCauses = async () => {
    if (causesAsked.current) return
    causesAsked.current = true
    try {
      const r = await request<CausesOut>('POST', `${base}/causes`)
      setCauses(r.causes ?? {})
    } catch {
      // nothing to show
    }
  }

  const load = async () => {
    if (!validId) return
    const mine = ++seq.current
    try {
      const d = await request<QuestionDetailOut>('GET', base)
      if (mine !== seq.current) return
      setDetail(d)
      triedRefresh.current = false
      loaded.current = true
      setState('ok')
      if (!d.is_subjective && d.groups.length > 0) void loadCauses()
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
  const openResult = (submissionId: number) => {
    void Taro.navigateTo({ url: `/pages/results/detail/index?submissionId=${submissionId}` })
  }

  /** Signed crop URLs expire: refetch the detail once, then give up. */
  const onCropError = async () => {
    if (triedRefresh.current) return
    triedRefresh.current = true
    try {
      setDetail(await request<QuestionDetailOut>('GET', base))
    } catch {
      // leave the broken image
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
        <Text className='label'>找不到这道题</Text>
        <Button className='big-btn' onClick={back}>
          返回
        </Button>
      </View>
    )
  }
  if (state === 'error' || !detail) {
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

  const crops = detail.crops ?? []
  const cropUrls = crops.map((c) => c.crop_url)

  return (
    <View className='page'>
      <View className='card'>
        <Text className='title-lg' style={{ display: 'block' }}>第 {detail.question_no} 题</Text>
        {detail.knowledge_point ? (
          <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{detail.knowledge_point}</Text>
        ) : null}
        <Text className='label' style={{ marginTop: '16px' }}>
          全班 {detail.answered_count} 人作答，{detail.wrong_count} 人没拿满分
        </Text>
        {detail.question_text ? <Text style={{ display: 'block' }}>{detail.question_text}</Text> : null}
        <Text className='label' style={{ marginTop: '16px' }}>正确答案</Text>
        <Text style={{ display: 'block' }}>{detail.correct_answer ?? '（无）'}</Text>
      </View>

      {detail.is_subjective ? (
        <View className='card'>
          <Text className='label'>得分分布</Text>
          {detail.score_buckets.map((b) => (
            <View
              key={b.label}
              style={{ display: 'flex', justifyContent: 'space-between', marginTop: '12px' }}
            >
              <Text>{b.label}</Text>
              <Text className='strong'>{b.count} 人</Text>
            </View>
          ))}
        </View>
      ) : (
        <View>
          <Text className='title-md' style={{ display: 'block', margin: '8px 0 24px' }}>错答分布</Text>
          {detail.groups.length === 0 ? (
            <Text className='label'>这道题没有人答错</Text>
          ) : (
            detail.groups.map((g) => (
              <View className='card card-band band-danger' key={g.key}>
                <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text className='strong'>{g.answer || '（空白）'}</Text>
                  <Text className='label' style={{ marginBottom: 0 }}>{g.count} 人</Text>
                </View>
                <View style={{ display: 'flex', flexWrap: 'wrap', marginTop: '12px' }}>
                  {g.students.map((s) => (
                    <Text
                      key={s.submission_id}
                      className='link'
                      style={{ marginRight: '24px', marginBottom: '8px' }}
                      onClick={() => openResult(s.submission_id)}
                    >
                      {s.student_name}
                    </Text>
                  ))}
                </View>
                {causes[g.key] ? (
                  <View style={{ marginTop: '12px' }}>
                    <Text>{causes[g.key]}</Text>
                    <Text className='muted' style={{ fontSize: '20px', marginLeft: '12px' }}>{AI_LABEL}</Text>
                  </View>
                ) : null}
              </View>
            ))
          )}
        </View>
      )}

      {crops.length > 0 ? (
        <View>
          <Text className='title-md' style={{ display: 'block', margin: '8px 0 24px' }}>学生作答截图</Text>
          <View style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between' }}>
            {crops.map((c, i) => (
              <View key={`${c.submission_id}-${i}`} style={{ width: '31%', marginBottom: '16px' }}>
                <Image
                  src={c.crop_url}
                  mode='aspectFill'
                  style={{ width: '100%', height: '160px', background: 'var(--card)', borderRadius: '8px' }}
                  onError={() => void onCropError()}
                  onClick={() => void Taro.previewImage({ urls: cropUrls, current: c.crop_url })}
                />
                <Text
                  className='link'
                  style={{ display: 'block', fontSize: '20px', textAlign: 'center' }}
                  onClick={() => openResult(c.submission_id)}
                >
                  {c.student_name}
                </Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}
    </View>
  )
}
