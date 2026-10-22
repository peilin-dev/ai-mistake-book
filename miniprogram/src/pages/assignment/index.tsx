import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter, useUnload } from '@tarojs/taro'
import { ApiError, request } from '../../lib/api'
import { errorText, failReasonAction, failReasonText, pageStatusText } from '../../lib/messages'
import {
  answerKeyAction,
  assignmentHints,
  bottomActions,
  isFinished,
  orderPages,
  progressText,
  unassignedPageCount,
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
  const busy = useRef(new Set<number>())

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
      if (!loaded.current && e instanceof ApiError && e.status === 404) {
        setState('notfound')
      } else if (!loaded.current) {
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
    if (busy.current.has(pageId)) return
    busy.current.add(pageId)
    setBusyPages([...busy.current])
    try {
      await request('POST', `/api/pages/${pageId}:retry`)
    } catch (e) {
      // 409: it is already being retried, nothing to tell the teacher
      if (!(e instanceof ApiError && e.status === 409)) {
        Taro.showToast({ title: errorText(e), icon: 'none' })
      }
    }
    try {
      await refresh()
    } finally {
      busy.current.delete(pageId)
      setBusyPages([...busy.current])
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

  const subjectLabel = SUBJECTS.find((s) => s.value === assignment.subject)?.label ?? '其他'
  const keyAction = answerKeyAction(assignment.answer_key_status)
  const text = progressText(progress, submissions, rosterSize)
  const hints = assignmentHints(assignment, rosterSize)
  const bottom = bottomActions(progress, submissions.length, unassignedPageCount(pages))
  const id = assignment.id

  return (
    <View className='page' style={{ paddingBottom: '420px' }}>
      <View className='card'>
        <Text className='title-xl' style={{ display: 'block' }}>{assignment.title}</Text>
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
        {keyAction === 'confirmed' ? <Text className='text-ok'>✓ 已确认答案卷</Text> : null}
      </View>

      <View className='card'>
        <Text style={{ fontSize: '34px', display: 'block' }}>{text.pages}</Text>
        {progress.failed > 0 ? (
          <Text className='text-danger' style={{ display: 'block', marginTop: '8px' }}>{progress.failed} 张没批成</Text>
        ) : null}
        {rosterSize > 0 ? (
          <Text className='label' style={{ marginTop: '8px' }}>
            {text.students}
          </Text>
        ) : null}
        {hints.map((h) => (
          <Text key={h} className='label' style={{ color: 'var(--warn-text)' }}>
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
        orderPages(pages).map((p) => {
          const action = p.status === 'failed' ? failReasonAction(p.fail_reason) : null
          return (
            <View className={p.status === 'failed' ? 'card card-band band-danger' : 'card'} key={p.page_id}>
              <View style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text className='strong'>
                  第 {p.seq} 张　{p.student_name ?? '未识别'}
                </Text>
                <Text
                  className='label'
                  style={{ marginBottom: 0, color: p.status === 'failed' ? 'var(--danger)' : undefined }}
                >
                  {pageStatusText(p.status)}
                </Text>
              </View>
              {p.status === 'failed' ? (
                <View style={{ marginTop: '16px' }}>
                  <Text className='text-danger' style={{ display: 'block', marginBottom: '16px' }}>
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
            {bottom.reviewLabel}
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
