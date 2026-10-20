import { useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { request } from '../../lib/api'
import { errorText } from '../../lib/messages'
import { classCardStatus } from '../../lib/classCard'
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

  if (cards === null) return <View className='page' />

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
      {cards.map(({ cls, studentCount, latest, progress }) => {
        const status = classCardStatus(latest, progress)
        return (
          <View className='card' key={cls.id} onClick={() => openClass(cls.id)}>
            <View style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text style={{ fontSize: '36px', fontWeight: 'bold' }}>{cls.name}</Text>
              {studentCount !== null ? <Text style={{ color: '#777' }}>{studentCount} 人</Text> : null}
            </View>
            {latest ? (
              <View style={{ marginTop: '16px' }}>
                <Text style={{ marginRight: '16px' }}>{latest.title}</Text>
                <StatusPill text={status.text} tone={status.tone} />
              </View>
            ) : (
              <View style={{ marginTop: '16px' }}>
                <StatusPill text={status.text} tone={status.tone} />
              </View>
            )}
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
