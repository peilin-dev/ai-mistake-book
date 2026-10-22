import { useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { request } from '../../lib/api'
import { errorText } from '../../lib/messages'
import { classCardStatus, gradedPercent } from '../../lib/classCard'
import type { AssignmentOut, ClassOut, ProgressOut } from '../../lib/types'
import NewAssignmentSheet from '../../components/NewAssignmentSheet'
import StatusPill from '../../components/StatusPill'

interface Row {
  assignment: AssignmentOut
  progress: ProgressOut | null
}

type LoadState = 'loading' | 'ok' | 'error' | 'notfound'

export default function ClassDetail() {
  const classId = Number(useRouter().params.classId)
  const validId = Number.isInteger(classId) && classId > 0
  const [state, setState] = useState<LoadState>(validId ? 'loading' : 'notfound')
  const [cls, setCls] = useState<ClassOut | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [lastSubject, setLastSubject] = useState<string | null>(null)
  const [sheet, setSheet] = useState(false)
  const loadSeq = useRef(0)

  const load = async () => {
    if (!validId) return
    const seq = ++loadSeq.current
    try {
      const [classes, me, assignments] = await Promise.all([
        request<ClassOut[]>('GET', '/api/classes'),
        request<{ last_subject: string | null }>('GET', '/api/me').catch(() => null),
        request<AssignmentOut[]>('GET', `/api/classes/${classId}/assignments`),
      ])
      if (seq !== loadSeq.current) return
      const found = classes.find((c) => c.id === classId) ?? null
      setCls(found)
      setLastSubject(me ? me.last_subject : null)
      if (!found) {
        setState('notfound')
        return
      }
      // Show the list now; progress pills fill in as each request returns.
      setRows((old) =>
        assignments.map((assignment) => ({
          assignment,
          progress: old.find((r) => r.assignment.id === assignment.id)?.progress ?? null,
        })),
      )
      setState('ok')
      assignments.forEach((assignment) => {
        request<ProgressOut>('GET', `/api/assignments/${assignment.id}/progress`)
          .then((progress) => {
            if (seq !== loadSeq.current) return
            setRows((old) => old.map((r) => (r.assignment.id === assignment.id ? { ...r, progress } : r)))
          })
          .catch(() => undefined)
      })
    } catch (e) {
      if (seq !== loadSeq.current) return
      Taro.showToast({ title: errorText(e), icon: 'none' })
      setState((old) => (old === 'ok' ? 'ok' : 'error'))
    }
  }

  useDidShow(() => {
    void load()
  })

  const retry = () => {
    setState('loading')
    void load()
  }
  const toClassList = () => {
    void Taro.reLaunch({ url: '/pages/index/index' })
  }
  const openRoster = () => {
    void Taro.navigateTo({ url: `/pages/class-edit/index?classId=${classId}` })
  }
  const openAssignment = (id: number) => {
    void Taro.navigateTo({ url: `/pages/assignment/index?assignmentId=${id}` })
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
        <Text className='label'>找不到这个班级</Text>
        <Button className='big-btn' onClick={toClassList}>
          回到班级列表
        </Button>
      </View>
    )
  }
  if (state === 'error') {
    return (
      <View className='page'>
        <Text className='label' onClick={retry}>
          加载失败，点这里重试
        </Text>
      </View>
    )
  }

  return (
    <View className='page'>
      <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <Text className='title-xl'>{cls ? cls.name : '班级'}</Text>
        <Text className='link' style={{ padding: '12px 0 12px 24px' }} onClick={openRoster}>
          名单
        </Text>
      </View>
      {rows.length === 0 ? (
        <Text className='label'>还没有作业，点下面的“新建作业”开始</Text>
      ) : (
        rows.map(({ assignment, progress }) => {
          const status = classCardStatus(assignment, progress)
          const percent = gradedPercent(progress)
          return (
            <View className={`card card-band band-${status.tone}`} key={assignment.id} onClick={() => openAssignment(assignment.id)}>
              <Text className='title-md' style={{ marginRight: '16px' }}>{assignment.title}</Text>
              <View style={{ marginTop: '16px' }}>
                <StatusPill text={status.text} tone={status.tone} />
              </View>
              {percent !== null ? (
                <View className='progress'>
                  <View className={`progress-fill fill-${status.tone}`} style={{ width: `${percent}%` }} />
                </View>
              ) : null}
            </View>
          )
        })
      )}
      <View className='bottom-bar'>
        <Button className='big-btn' onClick={() => setSheet(true)}>
          新建作业
        </Button>
      </View>
      {sheet && cls ? (
        <NewAssignmentSheet
          classId={classId}
          grade={cls.grade}
          lastSubject={lastSubject}
          onClose={() => setSheet(false)}
        />
      ) : null}
    </View>
  )
}