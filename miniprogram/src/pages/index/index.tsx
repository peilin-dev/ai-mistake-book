import { useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { request } from '../../lib/api'
import { errorText } from '../../lib/messages'
import { classCardStatus, gradedPercent, todayLine } from '../../lib/classCard'
import type { AssignmentOut, ClassOut, ProgressOut, StudentOut } from '../../lib/types'
import EmptyGuide from '../../components/EmptyGuide'
import StatusPill from '../../components/StatusPill'

interface Card {
  cls: ClassOut
  studentCount: number | null
  latest: AssignmentOut | null
  progress: ProgressOut | null
}

async function loadCard(cls: ClassOut): Promise<Card> {
  const [students, assignments] = await Promise.all([
    request<StudentOut[]>('GET', `/api/classes/${cls.id}/students`).catch(() => null),
    request<AssignmentOut[]>('GET', `/api/classes/${cls.id}/assignments`).catch(() => null),
  ])
  const latest = assignments && assignments.length > 0 ? assignments[0] : null
  const progress = latest
    ? await request<ProgressOut>('GET', `/api/assignments/${latest.id}/progress`).catch(() => null)
    : null
  return { cls, studentCount: students ? students.length : null, latest, progress }
}

export default function Index() {
  const [cards, setCards] = useState<Card[] | null>(null)

  const load = async () => {
    try {
      const classes = await request<ClassOut[]>('GET', '/api/classes')
      setCards(await Promise.all(classes.map(loadCard)))
    } catch (e) {
      Taro.showToast({ title: errorText(e), icon: 'none' })
      setCards((old) => old ?? [])
    }
  }

  useDidShow(() => {
    void load()
  })

  const newClass = () => {
    void Taro.navigateTo({ url: '/pages/class-edit/index' })
  }
  const openClass = (id: number) => {
    void Taro.navigateTo({ url: `/pages/class/index?classId=${id}` })
  }

  if (cards === null) {
    return (
      <View className='page'>
        <Text className='label'>加载中…</Text>
      </View>
    )
  }

  if (cards.length === 0) {
    return (
      <EmptyGuide
        title='欢迎使用'
        hint='先建一个班，粘贴学生名单，就可以开始拍卷了'
        buttonText='先建一个班'
        onClick={newClass}
      />
    )
  }

  return (
    <View className='page'>
      <Text className='date-line'>{todayLine(new Date())}</Text>
      {cards.map(({ cls, studentCount, latest, progress }) => {
        const status = classCardStatus(latest, progress)
        const percent = gradedPercent(progress)
        return (
          <View className={`card card-band band-${status.tone}`} key={cls.id} onClick={() => openClass(cls.id)}>
            <View style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <Text className='title-lg'>{cls.name}</Text>
              {studentCount !== null ? <Text className='muted'>{studentCount} 人</Text> : null}
            </View>
            {latest ? (
              <View style={{ marginTop: '16px' }}>
                <Text style={{ marginRight: '16px', color: 'var(--ink-2)' }}>{latest.title}</Text>
                <StatusPill text={status.text} tone={status.tone} />
              </View>
            ) : (
              <View style={{ marginTop: '16px' }}>
                <StatusPill text={status.text} tone={status.tone} />
              </View>
            )}
            {percent !== null ? (
              <View className='progress'>
                <View className={`progress-fill fill-${status.tone}`} style={{ width: `${percent}%` }} />
              </View>
            ) : null}
          </View>
        )
      })}
      <View className='bottom-bar'>
        <Button className='big-btn ghost-btn' onClick={newClass}>
          新建班级
        </Button>
      </View>
    </View>
  )
}
