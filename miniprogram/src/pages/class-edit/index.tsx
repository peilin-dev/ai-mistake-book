import { useEffect, useRef, useState } from 'react'
import { View, Text, Button, Input, Textarea, Picker } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { request } from '../../lib/api'
import { errorText } from '../../lib/messages'
import { previewRoster } from '../../lib/roster'
import { DEFAULT_GRADE, GRADE_LABELS, defaultClassName } from '../../lib/grades'
import type { ClassOut, StudentOut } from '../../lib/types'

const ROSTER_PLACEHOLDER = '每行一个学生，可带学号，例如：\n张三\n李四 02\n王五,03'

function toast(title: string) {
  void Taro.showToast({ title, icon: 'none', duration: 2500 })
}

function goHome() {
  if (Taro.getCurrentPages().length > 1) void Taro.navigateBack()
  else void Taro.reLaunch({ url: '/pages/index/index' })
}

function RosterBox({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { count } = previewRoster(value)
  return (
    <View>
      <Textarea
        className='field'
        style={{ minHeight: '280px', width: 'auto' }}
        placeholder={ROSTER_PLACEHOLDER}
        maxlength={-1}
        autoHeight
        value={value}
        onInput={(e) => onChange(e.detail.value)}
      />
      <Text className='label'>{count > 0 ? `识别到 ${count} 人` : '把名单从微信或表格里粘贴到这里'}</Text>
    </View>
  )
}

function NewClass() {
  const [grade, setGrade] = useState(DEFAULT_GRADE)
  const [name, setName] = useState(defaultClassName(DEFAULT_GRADE))
  const [nameTouched, setNameTouched] = useState(false)
  const [roster, setRoster] = useState('')
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)

  const pickGrade = (g: number) => {
    setGrade(g)
    if (!nameTouched) setName(defaultClassName(g))
  }

  const submit = async () => {
    const className = name.trim()
    if (!className) {
      toast('请先填写班级名称')
      return
    }
    if (submitting.current) return
    submitting.current = true
    setBusy(true)
    try {
      let cls: ClassOut
      try {
        cls = await request<ClassOut>('POST', '/api/classes', { name: className, grade })
      } catch (e) {
        toast(errorText(e))
        return
      }
      if (previewRoster(roster).count > 0) {
        try {
          await request('POST', `/api/classes/${cls.id}/students:import`, { text: roster })
        } catch (e) {
          await Taro.showModal({
            title: '班级已建好',
            content: `名单还没导入成功：${errorText(e)}。可以在名单页重新追加。`,
            showCancel: false,
          })
          void Taro.redirectTo({ url: `/pages/class-edit/index?classId=${cls.id}` })
          return
        }
      }
      goHome()
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  const count = previewRoster(roster).count
  return (
    <View className='page'>
      <Text className='label'>年级</Text>
      <Picker
        mode='selector'
        range={GRADE_LABELS}
        value={grade - 1}
        onChange={(e) => pickGrade(Number(e.detail.value) + 1)}
      >
        <View className='field'>{GRADE_LABELS[grade - 1]}</View>
      </Picker>
      <Text className='label'>班级名称</Text>
      <Input
        className='field'
        value={name}
        maxlength={32}
        onInput={(e) => {
          setName(e.detail.value)
          setNameTouched(true)
        }}
      />
      <Text className='label'>学生名单（可以先不填，之后再追加）</Text>
      <RosterBox value={roster} onChange={setRoster} />
      <View className='bottom-bar'>
        <Button className='big-btn' loading={busy} disabled={busy} onClick={submit}>
          {count > 0 ? `建班并导入 ${count} 人` : '建班'}
        </Button>
      </View>
    </View>
  )
}

function StudentRow({ s, onChanged }: { s: StudentOut; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(s.name)
  const [no, setNo] = useState(s.student_no ?? '')

  const open = () => {
    setName(s.name)
    setNo(s.student_no ?? '')
    setEditing(true)
  }

  const save = async () => {
    const n = name.trim()
    if (!n) {
      toast('姓名不能为空')
      return
    }
    try {
      await request('PATCH', `/api/students/${s.id}`, { name: n, student_no: no.trim() || null })
      setEditing(false)
      onChanged()
    } catch (e) {
      toast(errorText(e))
    }
  }

  const remove = async () => {
    const r = await Taro.showModal({ title: `删除 ${s.name}？`, content: '删除后不能恢复。' })
    if (!r.confirm) return
    try {
      await request('DELETE', `/api/students/${s.id}`)
      onChanged()
    } catch (e) {
      // 409 carries the backend's Chinese detail (students with results can't be deleted)
      await Taro.showModal({ title: '不能删除', content: errorText(e), showCancel: false })
    }
  }

  if (!editing) {
    return (
      <View className='card' style={{ display: 'flex', justifyContent: 'space-between' }} onClick={open}>
        <Text>{s.name}</Text>
        <Text style={{ color: '#777' }}>{s.student_no ? `学号 ${s.student_no}` : '点击修改'}</Text>
      </View>
    )
  }
  return (
    <View className='card'>
      <Text className='label'>姓名</Text>
      <Input className='field' value={name} maxlength={64} onInput={(e) => setName(e.detail.value)} />
      <Text className='label'>学号（可不填）</Text>
      <Input className='field' value={no} onInput={(e) => setNo(e.detail.value)} />
      <View style={{ display: 'flex', gap: '16px' }}>
        <Button className='big-btn' style={{ flex: 1 }} onClick={save}>
          保存
        </Button>
        <Button className='big-btn ghost-btn' style={{ flex: 1 }} onClick={() => setEditing(false)}>
          取消
        </Button>
        <Button className='big-btn ghost-btn' style={{ flex: 1, color: '#d93025', borderColor: '#d93025' }} onClick={remove}>
          删除
        </Button>
      </View>
    </View>
  )
}

function EditClass({ classId }: { classId: number }) {
  const [students, setStudents] = useState<StudentOut[] | null>(null)
  const [roster, setRoster] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      setStudents(await request<StudentOut[]>('GET', `/api/classes/${classId}/students`))
    } catch (e) {
      toast(errorText(e))
      setStudents((old) => old ?? [])
    }
  }

  useEffect(() => {
    void load()
    request<ClassOut[]>('GET', '/api/classes')
      .then((list) => {
        const c = list.find((x) => x.id === classId)
        void Taro.setNavigationBarTitle({ title: c ? `${c.name} 名单` : '班级名单' })
      })
      .catch(() => {
        void Taro.setNavigationBarTitle({ title: '班级名单' })
      })
  }, [classId])

  const append = async () => {
    setBusy(true)
    try {
      const r = await request<{ created: number }>('POST', `/api/classes/${classId}/students:import`, {
        text: roster,
      })
      setRoster('')
      toast(r.created > 0 ? `已追加 ${r.created} 人` : '这些学生已经在名单里了')
      await load()
    } catch (e) {
      toast(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const count = previewRoster(roster).count
  return (
    <View className='page'>
      <Text className='label'>{students ? `共 ${students.length} 人，点一行可以改名、改学号` : '加载中…'}</Text>
      {students?.map((s) => <StudentRow key={`${s.id}-${s.name}-${s.student_no}`} s={s} onChanged={load} />)}
      <Text className='label' style={{ marginTop: '32px' }}>
        追加名单
      </Text>
      <RosterBox value={roster} onChange={setRoster} />
      <View className='bottom-bar'>
        <Button className='big-btn' loading={busy} disabled={busy || count === 0} onClick={append}>
          {count > 0 ? `追加名单（${count} 人）` : '追加名单'}
        </Button>
      </View>
    </View>
  )
}

export default function ClassEdit() {
  const { params } = useRouter()
  const classId = params.classId ? Number(params.classId) : null
  return classId ? <EditClass classId={classId} /> : <NewClass />
}
