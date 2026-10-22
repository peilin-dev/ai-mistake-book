import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { ApiError, request } from '../../lib/api'
import { avgText, overviewNotices, percent, questionLine } from '../../lib/analytics'
import { errorText } from '../../lib/messages'
import ExportSheet from '../../components/ExportSheet'
import type { AnalyticsOut } from '../../lib/types'

type LoadState = 'loading' | 'ok' | 'error' | 'notfound'

/** accuracy < 60% red, < 85% orange, otherwise green; unknown accuracy is gray. */
function tone(accuracy: number | null): { band: string; fill: string } {
  if (accuracy === null) return { band: 'band-gray', fill: '' }
  if (accuracy < 0.6) return { band: 'band-danger', fill: 'fill-danger' }
  if (accuracy < 0.85) return { band: 'band-warn', fill: 'fill-warn' }
  return { band: 'band-ok', fill: 'fill-ok' }
}

export default function AnalyticsPage() {
  const assignmentId = Number(useRouter().params.assignmentId)
  const validId = Number.isInteger(assignmentId) && assignmentId > 0
  const [state, setState] = useState<LoadState>(validId ? 'loading' : 'notfound')
  const [data, setData] = useState<AnalyticsOut | null>(null)
  const [exporting, setExporting] = useState(false)
  const seq = useRef(0)
  const loaded = useRef(false)

  const load = async () => {
    if (!validId) return
    const mine = ++seq.current
    try {
      const a = await request<AnalyticsOut>('GET', `/api/assignments/${assignmentId}/analytics`)
      if (mine !== seq.current) return
      setData(a)
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
  const go = (url: string) => {
    void Taro.navigateTo({ url })
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
  if (state === 'error' || !data) {
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

  const notices = overviewNotices(data)
  const wrongQuestions = data.questions.filter((q) => q.wrong_count > 0)
  const cell = { flex: 1, textAlign: 'center' as const }

  return (
    <View className='page'>
      <Button className='big-btn ghost-btn' style={{ marginBottom: '48rpx' }} onClick={() => setExporting(true)}>
        导出 PDF
      </Button>
      {wrongQuestions.length > 0 ? (
        <Button
          className='big-btn ghost-btn'
          style={{ marginBottom: '48rpx' }}
          onClick={() => go(`/pages/practice/index?assignmentId=${assignmentId}`)}
        >
          生成练习纸
        </Button>
      ) : null}
      {exporting ? (
        <ExportSheet
          assignmentId={assignmentId}
          items={[
            { kind: 'lecture', label: '班级讲评单', hint: '错得多的题，适合讲评课' },
            { kind: 'class_students', label: '全班错题单', hint: '每位同学一份，发给学生订正' },
          ]}
          onClose={() => setExporting(false)}
        />
      ) : null}
      <View className='card' style={{ display: 'flex' }}>
        <View style={cell}>
          <Text className='title-xl' style={{ display: 'block' }}>{avgText(data.average_score)}</Text>
          <Text className='label'>平均分</Text>
        </View>
        <View style={cell}>
          <Text className='title-xl' style={{ display: 'block' }}>{percent(data.pass_rate)}</Text>
          <Text className='label'>及格率</Text>
        </View>
        <View style={cell}>
          <Text className='title-xl' style={{ display: 'block' }}>
            {data.counted_students} / {data.roster_size}
          </Text>
          <Text className='label'>已出成绩</Text>
        </View>
      </View>

      {notices.map((n) =>
        n.action === 'review' ? (
          <Text
            key={n.text}
            className='label hint link'
            onClick={() => go(`/pages/review/index?assignmentId=${assignmentId}`)}
          >
            {n.text}　去复核 ›
          </Text>
        ) : (
          <Text key={n.text} className='label hint'>
            {n.text}
          </Text>
        ),
      )}

      <Text className='title-lg' style={{ display: 'block', margin: '16px 0 24px' }}>错得最多的题</Text>
      {wrongQuestions.length === 0 ? (
        <Text className='label'>{data.counted_students === 0 ? '还没有出成绩的卷子' : '这次没有错题，全班都做对了'}</Text>
      ) : (
        wrongQuestions.map((q) => {
          const t = tone(q.accuracy)
          return (
            <View
              className={`card card-band ${t.band}`}
              key={q.question_no}
              onClick={() =>
                go(`/pages/analytics/question/index?assignmentId=${assignmentId}&no=${encodeURIComponent(q.question_no)}`)
              }
            >
              <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text className='strong'>第 {q.question_no} 题</Text>
                <Text className='label' style={{ marginBottom: 0 }}>
                  错 {q.wrong_count} / {q.student_count} 人 ›
                </Text>
              </View>
              {q.knowledge_point ? (
                <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{q.knowledge_point}</Text>
              ) : null}
              <View className='progress'>
                <View
                  className={`progress-fill ${t.fill}`}
                  style={{ width: `${Math.round((q.accuracy ?? 0) * 100)}%` }}
                />
              </View>
              <Text className='label' style={{ marginTop: '12px', marginBottom: 0 }}>{questionLine(q)}</Text>
            </View>
          )
        })
      )}

      {data.weak_points.length > 0 ? (
        <View className='card'>
          <Text className='label'>薄弱知识点</Text>
          <Text>{data.weak_points.map((w) => `${w.name}（错 ${w.wrong_count}）`).join('　')}</Text>
        </View>
      ) : null}

      {data.attention.length > 0 ? (
        <View>
          <Text className='title-lg' style={{ display: 'block', margin: '16px 0 24px' }}>需要关注的学生</Text>
          {data.attention.map((s) => (
            <View
              className='card card-band band-danger'
              key={s.student_id}
              onClick={() => go(`/pages/results/detail/index?submissionId=${s.submission_id}`)}
            >
              <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text className='strong'>{s.student_name}</Text>
                <Text className='label' style={{ marginBottom: 0 }}>
                  {avgText(s.score)} / {avgText(s.max_score)} 分　错 {s.wrong_count} 题 ›
                </Text>
              </View>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  )
}
