import { Text } from '@tarojs/components'
import type { Tone } from '../lib/classCard'
import './components.scss'

export default function StatusPill({ text, tone }: { text: string; tone: Tone }) {
  if (!text) return null
  return <Text className={`pill pill-${tone}`}>{text}</Text>
}
