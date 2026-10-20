import { View, Text, Button } from '@tarojs/components'
import './components.scss'

interface Props {
  title: string
  hint?: string
  buttonText: string
  onClick: () => void
}

export default function EmptyGuide({ title, hint, buttonText, onClick }: Props) {
  return (
    <View className='empty-guide'>
      <Text className='empty-title'>{title}</Text>
      {hint ? <Text className='empty-hint'>{hint}</Text> : null}
      <Button className='big-btn' onClick={onClick}>
        {buttonText}
      </Button>
    </View>
  )
}
