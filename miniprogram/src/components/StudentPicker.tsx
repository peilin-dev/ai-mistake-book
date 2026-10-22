import { View, Text, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import type { StudentOut } from '../lib/types'
import './components.scss'

interface Props {
  students: StudentOut[]
  onPick: (s: StudentOut) => void
  onClose: () => void
  /** Roster page of this class; shows "名单里没有这个学生？去添加" when given. */
  addUrl?: string | null
}

/** Bottom sheet: tap a name to choose that student. */
export default function StudentPicker({ students, onPick, onClose, addUrl }: Props) {
  const goAdd = () => {
    if (!addUrl) return
    onClose()
    void Taro.navigateTo({ url: addUrl })
  }
  return (
    <View className='sheet-mask' onClick={onClose}>
      <View className='sheet' onClick={(e) => e.stopPropagation()}>
        <Text className='sheet-title'>选择学生</Text>
        {students.length === 0 ? (
          <Text className='label'>这个班还没有名单，请先导入名单</Text>
        ) : (
          <ScrollView scrollY style={{ maxHeight: '700px' }}>
            {students.map((s) => (
              <View className='card picker-row' key={s.id} onClick={() => onPick(s)}>
                <Text style={{ fontSize: '34px' }}>{s.name}</Text>
                {s.student_no ? <Text className='label picker-no'>{s.student_no}</Text> : null}
              </View>
            ))}
          </ScrollView>
        )}
        {addUrl ? (
          <Text
            className='label'
            style={{ display: 'block', textAlign: 'center', color: 'var(--link)', padding: '24px 0 8px' }}
            onClick={goAdd}
          >
            名单里没有这个学生？去添加
          </Text>
        ) : null}
      </View>
    </View>
  )
}
