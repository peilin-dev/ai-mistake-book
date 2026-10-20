import { useRef, useState } from 'react'
import { View, Text, Button, Input } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { request } from '../lib/api'
import { errorText } from '../lib/messages'
import { defaultAssignmentTitle, defaultSubject } from '../lib/newAssignment'
import { subjectsForGrade } from '../lib/subjects'
import type { AssignmentOut } from '../lib/types'
import './components.scss'

interface Props {
  classId: number
  grade: number
  lastSubject: string | null
  onClose: () => void
}

export default function NewAssignmentSheet({ classId, grade, lastSubject, onClose }: Props) {
  const subjects = subjectsForGrade(grade)
  const [subject, setSubject] = useState(() => defaultSubject(subjects, lastSubject))
  const [title, setTitle] = useState(() => defaultAssignmentTitle(new Date()))
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)

  const create = async () => {
    if (submitting.current) return
    submitting.current = true
    setBusy(true)
    try {
      const finalTitle = title.trim() || defaultAssignmentTitle(new Date())
      const a = await request<AssignmentOut>('POST', '/api/assignments', {
        class_id: classId,
        subject,
        title: finalTitle,
      })
      onClose()
      void Taro.navigateTo({ url: `/pages/assignment/index?assignmentId=${a.id}` })
    } catch (e) {
      Taro.showToast({ title: errorText(e), icon: 'none' })
      submitting.current = false
      setBusy(false)
    }
  }

  return (
    <View className='sheet-mask' onClick={onClose}>
      <View className='sheet' onClick={(e) => e.stopPropagation()}>
        <Text className='sheet-title'>新建作业</Text>
        <Text className='label'>学科</Text>
        <View className='subject-list'>
          {subjects.map((s) => (
            <Text
              key={s.value}
              className={`subject-chip${s.value === subject ? ' subject-on' : ''}`}
              onClick={() => setSubject(s.value)}
            >
              {s.label}
            </Text>
          ))}
        </View>
        <Text className='label'>标题</Text>
        <Input
          className='field'
          value={title}
          maxlength={64}
          onInput={(e) => setTitle(e.detail.value)}
        />
        <Button className='big-btn' disabled={busy} loading={busy} onClick={create}>
          创建
        </Button>
      </View>
    </View>
  )
}
