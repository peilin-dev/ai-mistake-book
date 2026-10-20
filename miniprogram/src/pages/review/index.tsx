import { useEffect, useRef, useState } from 'react'
import { View, Text, Button, Image, Input } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { ApiError, request } from '../../lib/api'
import { errorText } from '../../lib/messages'
import {
  buildQueue,
  deferSkipped,
  parseScore,
  reasonText,
  refreshesExpiredImageUrls,
  skipHead,
  type ReviewItem,
} from '../../lib/review'
import type { AssignmentOut, ReviewOut, StudentOut } from '../../lib/types'
import StudentPicker from '../../components/StudentPicker'

type LoadState = 'loading' | 'ok' | 'error' | 'notfound'

export default function Review() {
  const assignmentId = Number(useRouter().params.assignmentId)
  const validId = Number.isInteger(assignmentId) && assignmentId > 0
  const [state, setState] = useState<LoadState>(validId ? 'loading' : 'notfound')
  const [items, setItems] = useState<ReviewItem[]>([]) // what is left; the head is shown
  const [doneCount, setDoneCount] = useState(0)
  const [students, setStudents] = useState<StudentOut[]>([])
  const [picking, setPicking] = useState(false)
  const [scoring, setScoring] = useState(false)
  const [scoreText, setScoreText] = useState('')
  const [busy, setBusy] = useState(false)
  const working = useRef(false)
  const classId = useRef<number | null>(null)
  /** Keys the teacher put off with 先跳过, oldest first; they stay at the back across reloads. */
  const skipped = useRef<string[]>([])
  const fetchReview = () => request<ReviewOut>('GET', `/api/assignments/${assignmentId}/review`)
  const refresher = useRef(refreshesExpiredImageUrls(fetchReview))
  const queueFrom = (r: ReviewOut) => deferSkipped(buildQueue(r), skipped.current)

  const load = async () => {
    if (!validId) return
    try {
      const a = await request<AssignmentOut>('GET', `/api/assignments/${assignmentId}`)
      classId.current = a.class_id
      const [roster, review] = await Promise.all([
        request<StudentOut[]>('GET', `/api/classes/${a.class_id}/students`),
        fetchReview(),
      ])
      setStudents(roster)
      setItems(queueFrom(review))
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

  useEffect(() => {
    void load()
  }, [])

  // Back from 去添加 (class-edit): pick up students added there.
  useDidShow(() => {
    if (classId.current === null) return
    request<StudentOut[]>('GET', `/api/classes/${classId.current}/students`)
      .then(setStudents)
      .catch(() => undefined)
  })

  const retryLoad = () => {
    setState('loading')
    void load()
  }
  const back = () => {
    if (Taro.getCurrentPages().length > 1) void Taro.navigateBack()
    else void Taro.reLaunch({ url: '/pages/index/index' })
  }

  /** Run one action on the head item; a second tap while it runs is ignored. */
  const act = async (fn: () => Promise<void>) => {
    if (working.current) return
    working.current = true
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 409)) {
        // This item changed elsewhere (already handled, page re-shot…): don't stay stuck on it.
        await reloadQueue('这一项已经变了，已为你刷新')
      } else {
        Taro.showToast({ title: errorText(e), icon: 'none' })
      }
    } finally {
      working.current = false
      setBusy(false)
    }
  }

  const reloadQueue = async (notice: string) => {
    try {
      setItems(queueFrom(await fetchReview()))
      setScoring(false)
      setScoreText('')
      Taro.showToast({ title: notice, icon: 'none' })
    } catch (e) {
      Taro.showToast({ title: errorText(e), icon: 'none' })
    }
  }

  /** 先跳过: put the head item at the back so everything behind it stays reachable. */
  const skipItem = () => {
    if (working.current) return
    setItems((old) => {
      const head = old[0]
      if (head) skipped.current = [...skipped.current.filter((k) => k !== head.key), head.key]
      return skipHead(old)
    })
    setPicking(false)
    setScoring(false)
    setScoreText('')
  }

  const addStudentUrl = () =>
    classId.current === null ? null : `/pages/class-edit/index?classId=${classId.current}`

  const advance = () => {
    setItems((old) => old.slice(1))
    setDoneCount((n) => n + 1)
    setScoring(false)
    setScoreText('')
  }

  const judge = (id: number, body: { is_correct?: boolean; score?: number }) =>
    act(async () => {
      await request('PATCH', `/api/question-results/${id}`, body)
      advance()
    })

  const submitScore = (id: number, max: number | null) => {
    const score = parseScore(scoreText, max)
    if (score === null) {
      Taro.showToast({
        title: max === null ? '请输入不小于 0 的分数' : `请输入 0 到 ${max} 之间的分数`,
        icon: 'none',
      })
      return
    }
    void judge(id, { score })
  }

  const assign = (pageId: number, s: StudentOut) => {
    setPicking(false)
    void act(async () => {
      await request('PATCH', `/api/pages/${pageId}`, { student_id: s.id })
      // The follow-up pages moved with this one, so the queue may have changed: reload it.
      try {
        setItems(queueFrom(await fetchReview()))
        setDoneCount((n) => n + 1)
      } catch {
        advance()
      }
    })
  }

  const onImageError = async (item: ReviewItem) => {
    const fresh = await refresher.current(item)
    if (fresh) setItems((old) => old.map((i) => (i.key === fresh.key ? fresh : i)))
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
        <Button className='big-btn' onClick={retryLoad}>
          重新加载
        </Button>
        <Button className='big-btn ghost-btn' style={{ marginTop: '16px' }} onClick={back}>
          返回
        </Button>
      </View>
    )
  }

  const item = items[0]
  if (!item) {
    return (
      <View className='page'>
        <View className='card' style={{ textAlign: 'center' }}>
          <Text style={{ fontSize: '44px', fontWeight: 'bold', display: 'block', marginBottom: '16px' }}>复核完成</Text>
          <Text className='label'>没有需要确认的内容了</Text>
        </View>
        <View className='bottom-bar'>
          <Button className='big-btn' onClick={back}>
            返回作业
          </Button>
        </View>
      </View>
    )
  }

  const total = doneCount + items.length
  const progress = `${doneCount + 1} / ${total}`

  if (item.kind === 'page') {
    return (
      <View className='page' style={{ paddingBottom: items.length > 1 ? '380px' : '260px' }}>
        <Text className='label'>第 {progress} 项</Text>
        <View className='card'>
          <Text style={{ fontSize: '36px', fontWeight: 'bold', display: 'block' }}>这张卷子是谁的？</Text>
          <Text className='label' style={{ marginTop: '8px' }}>
            识别到的名字：{item.recognizedName ?? '没认出名字'}
          </Text>
          {item.imageUrl ? (
            <Image
              key={item.imageUrl}
              src={item.imageUrl}
              mode='widthFix'
              style={{ width: '100%' }}
              onError={() => void onImageError(item)}
            />
          ) : (
            <Text className='label'>原图已删除</Text>
          )}
        </View>
        <View className='bottom-bar'>
          <Button className='big-btn' disabled={busy} onClick={() => setPicking(true)}>
            选择学生
          </Button>
          {items.length > 1 ? (
            <Button className='big-btn ghost-btn' style={{ marginTop: '16px' }} disabled={busy} onClick={skipItem}>
              先跳过
            </Button>
          ) : null}
        </View>
        {picking ? (
          <StudentPicker
            students={students}
            addUrl={addStudentUrl()}
            onPick={(s) => assign(item.pageId, s)}
            onClose={() => setPicking(false)}
          />
        ) : null}
      </View>
    )
  }

  const q = item.question
  const shot = q.crop_url ?? q.image_url
  return (
    <View className='page' style={{ paddingBottom: scoring ? '520px' : '400px' }}>
      <Text className='label'>第 {progress} 项</Text>
      <View className='card'>
        <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ fontSize: '36px', fontWeight: 'bold' }}>
            {q.student_name ?? '未识别学生'}　第 {q.question_no} 题
          </Text>
          <Text className='pill pill-warn'>{reasonText(q.reason)}</Text>
        </View>
        {shot ? (
          <Image
            key={shot}
            src={shot}
            mode='widthFix'
            style={{ width: '100%', marginTop: '16px' }}
            onError={() => void onImageError(item)}
            onClick={() => void Taro.previewImage({ urls: [shot] })}
          />
        ) : null}
        <Text className='label' style={{ marginTop: '16px' }}>题目</Text>
        <Text style={{ display: 'block' }}>{q.question_text}</Text>
        <Text className='label' style={{ marginTop: '16px' }}>学生答案</Text>
        <Text style={{ display: 'block' }}>{q.student_answer ?? '（没看清）'}</Text>
        <Text className='label' style={{ marginTop: '16px' }}>正确答案</Text>
        <Text style={{ display: 'block' }}>{q.correct_answer ?? '（无）'}</Text>
        <Text className='label' style={{ marginTop: '16px' }}>AI 判定</Text>
        <Text style={{ display: 'block', color: q.is_correct ? '#1d7a3a' : '#d93025' }}>
          {q.is_correct === null ? '没判出' : q.is_correct ? '对' : '错'}
          {q.score !== null ? `　${q.score}${q.max_score !== null ? ` / ${q.max_score}` : ''} 分` : ''}
        </Text>
      </View>
      <View className='bottom-bar'>
        {scoring ? (
          <View style={{ marginBottom: '16px' }}>
            <Text className='label'>
              改成几分？{q.max_score !== null ? `（0 到 ${q.max_score}）` : ''}
            </Text>
            <Input
              className='field'
              type='digit'
              focus
              placeholder='输入分数'
              value={scoreText}
              onInput={(e) => setScoreText(e.detail.value)}
            />
            <View style={{ display: 'flex' }}>
              <Button className='big-btn ghost-btn' style={{ marginRight: '16px' }} disabled={busy} onClick={() => setScoring(false)}>
                取消
              </Button>
              <Button className='big-btn' disabled={busy} onClick={() => submitScore(q.id, q.max_score)}>
                确定
              </Button>
            </View>
          </View>
        ) : (
          <View>
            <View style={{ display: 'flex' }}>
              <Button className='big-btn' style={{ marginRight: '16px' }} disabled={busy} onClick={() => void judge(q.id, { is_correct: true })}>
                判对
              </Button>
              <Button className='big-btn' style={{ marginRight: '16px', background: '#d93025' }} disabled={busy} onClick={() => void judge(q.id, { is_correct: false })}>
                判错
              </Button>
              <Button className='big-btn ghost-btn' disabled={busy} onClick={() => setScoring(true)}>
                改分
              </Button>
            </View>
            <View style={{ display: 'flex', marginTop: '16px' }}>
              <Button
                className='big-btn ghost-btn'
                style={items.length > 1 ? { marginRight: '16px' } : undefined}
                disabled={busy}
                onClick={() => setPicking(true)}
              >
                换学生
              </Button>
              {items.length > 1 ? (
                <Button className='big-btn ghost-btn' disabled={busy} onClick={skipItem}>
                  先跳过
                </Button>
              ) : null}
            </View>
          </View>
        )}
      </View>
      {picking ? (
        <StudentPicker
          students={students}
          addUrl={addStudentUrl()}
          onPick={(s) => assign(q.page_id, s)}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </View>
  )
}
