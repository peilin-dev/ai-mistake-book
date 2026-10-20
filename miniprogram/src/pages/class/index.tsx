import { useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { request } from '../../lib/api'
import { errorText } from '../../lib/messages'
import { classCardStatus } from '../../lib/classCard'
import type { AssignmentOut, ClassOut, ProgressOut } from '../../lib/types'
import NewAssignmentSheet from '../../components/NewAssignmentSheet'
import StatusPill from '../../components/StatusPill'

interface Row {
  assignment: AssignmentOut
  progress: ProgressOut | null
}

export default function ClassDetail() {
  const classId = Number(useRouter().params.classId)
  const [cls, setCls] = useState<ClassOut | null>(null)
  const [rows, setRows] = useState<Row[] | null>(null)
  const [lastSubject, setLastSubject] = useState<string | null>(null)
  const [sheet, setSheet] = useState(false)

  const load = async () => {
    try {
      const [classes, me, assignments] = await Promise.all([
        request<ClassOut[]>('GET', '/api/classes'),
        request<{ last_subject: string | null }>('GET', '/api/me').catch(() => null),
        request<AssignmentOut[]>('GET', `/api/classes/${classId}/assignments`),
      ])
      setCls(classes.find((c) => c.id === classId) ?? null)
      setLastSubject(me ? me.last_subject : null)
      const next = await Promise.all(
        assignments.map(async (assignment) => ({
          assignment,
          progress: await request<ProgressOut>('GET', `/api/assignments/${assignment.id}/progress`).catch(
            () => null,
          ),
        })),
      )
      setRows(next)
    } catch (e) {
      Taro.showToast({ title: errorText(e), icon: 'none' })
      setRows((old) => old ?? [])
    }
  }

  useDidShow(() => {
    void load()
  })

  const openRoster = () => {
    void Taro.navigateTo({ url: `/pages/class-edit/index?classId=${classId}` })
  }
  const openAssignment = (id: number) => {
    void Taro.navigateTo({ url: `/pages/assignment/index?assignmentId=${id}` })
  }

  if (rows === null) {
    return (
      <View className='page'>
        <Text className='label'>加载中…</Text>
      </View>
    )
  }

  return (
    <View className='page'>
      <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <Text style={{ fontSize: '40px', fontWeight: 'bold' }}>{cls ? cls.name : '班级'}</Text>
        <Text style={{ color: '#07c160', padding: '12px 0 12px 24px' }} onClick={openRoster}>
          名单
        </Text>
      </View>
      {rows.length === 0 ? (
        <Text className='label'>还没有作业，点下面的“新建作业”开始</Text>
      ) : (
        rows.map(({ assignment, progress }) => {
          const status = classCardStatus(assignment, progress)
          return (
            <View className='card' key={assignment.id} onClick={() => openAssignment(assignment.id)}>
              <Text style={{ fontSize: '34px', fontWeight: 'bold', marginRight: '16px' }}>{assignment.title}</Text>
              <View style={{ marginTop: '16px' }}>
                <StatusPill text={status.text} tone={status.tone} />
              </View>
            </View>
          )
        })
      )}
      <View className='bottom-bar'>
        <Button className='big-btn' disabled={!cls} onClick={() => setSheet(true)}>
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
