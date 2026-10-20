import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter, useUnload } from '@tarojs/taro'
import { request } from '../../lib/api'
import { errorText, failReasonAction, failReasonText } from '../../lib/messages'
import {
  answerKeyAction,
  assignmentHints,
  bottomActions,
  isFinished,
  progressText,
} from '../../lib/progress'
import { subjectsForGrade } from '../../lib/subjects'
import type { AssignmentOut, PageOut, ProgressOut, StudentOut, SubmissionOut } from '../../lib/types'

const POLL_MS = 3000
const SUBJECTS = subjectsForGrade(9)

type LoadState = 'loading' | 'ok' | 'error' | 'notfound'

export default function AssignmentHome() {
  const assignmentId = Number(useRouter().params.assignmentId)
  const validId = Number.isInteger(assignmentId) && assignmentId > 0
  const [state, setState] = useState<LoadState>(validId ? 'loading' : 'notfound')
  const [assignment, setAssignment] = useState<AssignmentOut | null>(null)
  const [rosterSize, setRosterSize] = useState(0)
  const [progress, setProgress] = useState<ProgressOut | null>(null)
  const [pages, setPages] = useState<PageOut[]>([])
  const [submissions, setSubmissions] = useState<SubmissionOut[]>([])
  const [busyPages, setBusyPages] = useState<number[]>([])
  const seq = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loaded = useRef(false)

  const stopPolling = () => {
    seq.current++ // any in-flight response is now stale
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
    }
  }

  /** Fetch everything once; then, unless all pages are finished, schedule the next round. */
  const refresh = async () => {
    if (!validId) return
    stopPolling()
    const mine = seq.current
    try {
      const a = await request<AssignmentOut>('GET', `/api/assignments/${assignmentId}`)
      const [roster, prog, pageList, subs] = await Promise.all([
        request<StudentOut[]>('GET', `/api/classes/${a.class_id}/students`),
        request<ProgressOut>('GET', `/api/assignments/${assignmentId}/progress`),
        request<PageOut[]>('GET', `/api/assignments/${assignmentId}/pages`),
        request<SubmissionOut[]>('GET', `/api/assignments/${assignmentId}/submissions`),
      ])
      if (mine !== seq.current) return
      setAssignment(a)
      setRosterSize(roster.length)
      setProgress(prog)
      setPages(pageList)
      setSubmissions(subs)
      loaded.current = true
      setState('ok')
      if (!isFinished(prog)) schedule()
    } catch (e) {
      if (mine !== seq.current) return
      if (!loaded.current) {
        Taro.showToast({ title: errorText(e), icon: 'none' })
        setState('error')
      } else {
        schedule()
      }
    }
  }

  /** Light poll: progress, pages and submissions only. */
  const poll = async () => {
    const mine = seq.current
    try {
      const [prog, pageList, subs] = await Promise.all([
        request<ProgressOut>('GET', `/api/assignments/${assignmentId}/progress`),
        request<PageOut[]>('GET', `/api/assignments/${assignmentId}/pages`),
        request<SubmissionOut[]>('GET', `/api/assignments/${assignmentId}/submissions`),
      ])
      if (mine !== seq.current) return
      setProgress(prog)
      setPages(pageList)
      setSubmissions(subs)
      if (!isFinished(prog)) schedule()
    } catch {
      if (mine !== seq.current) return
      schedule() // transient network trouble: keep the last good data, try again
    }
  }

  const schedule = () => {
    timer.current = setTimeout(() => {
      timer.current = null
      void poll()
    }, POLL_MS)
  }

  useDidShow(() => {
    void refresh()
  })
  useDidHide(stopPolling)
  useUnload(stopPolling)

  const retryLoad = () => {
    setState('loading')
    void refresh()
  }
  const back = () => {
    if (Taro.getCurrentPages().length > 1) void Taro.navigateBack()
    else void Taro.reLaunch({ url: '/pages/index/index' })
  }
  const go = (url: string) => {
    void Taro.navigateTo({ url })
  }

  const retryPage = async (pageId: number) => {
    if (busyPages.includes(pageId)) return
    setBusyPages((b) => [...b, pageId])
    try {
      await request('POST', `/api/pages/${pageId}:retry`)
    } catch (e) {
      Taro.showToast({ title: errorText(e), icon: 'none' })
    } finally {
      setBusyPages((b) => b.filter((id) => id !== pageId))
    }
    void refresh()
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
  if (state === 'error' || !assignment || !progress) {
    return (
      <View className='page'>
        <Text className='label' onClick={retryLoad}>
          加载失败，点这里重试
        </Text>
      </View>
    )
  }

  const subjectLabel = SUBJECTS.find((s) => s.value === assignment.subject)?.label ?? '其他'
  const keyAction = answerKeyAction(assignment.answer_key_status)
  const text = progressText(progress, submissions, rosterSize)
  const hints = assignmentHints(assignment, rosterSize)
  const bottom = bottomActions(progress, submissions.length)
  const id = assignment.id

  return (
    <View className='page' style={{ paddingBottom: '420px' }}>
      <View className='card'>
        <Text style={{ fontSize: '40px', fontWeight: 'bold', display: 'block' }}>{assignment.title}</Text>
        <Text className='label' style={{ marginTop: '8px' }}>
          {subjectLabel}
        </Text>
        {keyAction === 'shoot' ? (
          <Button className='big-btn' onClick={() => go(`/pages/camera/index?mode=answerKey&assignmentId=${id}`)}>
            拍答案卷
          </Button>
        ) : null}
        {keyAction === 'confirm' ? (
          <Button className='big-btn' onClick={() => go(`/pages/answer-key/index?assignmentId=${id}`)}>
            确认答案卷
          </Button>
        ) : null}
        {keyAction === 'confirmed' ? <Text style={{ color: '#1d7a3a' }}>✓ 已确认答案卷</Text> : null}
      </View>

      <View className='card'>
        <Text style={{ fontSize: '34px', display: 'block' }}>{text.pages}</Text>
        <Text className='label' style={{ marginTop: '8px' }}>
          {text.students}
        </Text>
        {hints.map((h) => (
          <Text key={h} className='label' style={{ color: '#8a6100' }}>
            {h}
          </Text>
        ))}
        {rosterSize === 0 ? (
          <Button
            className='big-btn ghost-btn'
            onClick={() => go(`/pages/class-edit/index?classId=${assignment.class_id}`)}
          >
            去导入
          </Button>
        ) : null}
      </View>

      {pages.length === 0 ? (
        <Text className='label'>还没有拍卷子，点下面的“开始拍卷”</Text>
      ) : (
        pages.map((p) => {
          const action = p.status === 'failed' ? failReasonAction(p.fail_reason) : null
          return (
            <View className='card' key={p.page_id}>
              <View style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text style={{ fontWeight: 'bold' }}>
                  第 {p.seq} 张　{p.student_name ?? '未识别'}
                </Text>
                <Text className='label' style={{ marginBottom: 0 }}>
                  {p.status === 'queued' ? '排队中' : p.status === 'processing' ? '批改中' : p.status === 'done' ? '已批完' : '没批成'}
                </Text>
              </View>
              {p.status === 'failed' ? (
                <View style={{ marginTop: '16px' }}>
                  <Text style={{ color: '#d93025', display: 'block', marginBottom: '16px' }}>
                    {failReasonText(p.fail_reason)}
                  </Text>
                  {action === 'retake' ? (
                    <Button
                      className='big-btn ghost-btn'
                      onClick={() =>
                        go(`/pages/camera/index?mode=replace&assignmentId=${id}&pageId=${p.page_id}`)
                      }
                    >
                      重拍
                    </Button>
                  ) : null}
                  {action === 'retry' ? (
                    <Button
                      className='big-btn ghost-btn'
                      disabled={busyPages.includes(p.page_id)}
                      onClick={() => void retryPage(p.page_id)}
                    >
                      重试
                    </Button>
                  ) : null}
                </View>
              ) : null}
            </View>
          )
        })
      )}

      <View className='bottom-bar'>
        <Button
          className={keyAction === 'shoot' ? 'big-btn ghost-btn' : 'big-btn'}
          onClick={() => go(`/pages/camera/index?mode=pages&assignmentId=${id}`)}
        >
          开始拍卷
        </Button>
        {bottom.review > 0 ? (
          <Button
            className='big-btn ghost-btn'
            style={{ marginTop: '16px' }}
            onClick={() => go(`/pages/review/index?assignmentId=${id}`)}
          >
            去复核 {bottom.review} 题
          </Button>
        ) : null}
        {bottom.results ? (
          <Button
            className='big-btn ghost-btn'
            style={{ marginTop: '16px' }}
            onClick={() => go(`/pages/results/index?assignmentId=${id}`)}
          >
            看成绩
          </Button>
        ) : null}
      </View>
    </View>
  )
}
