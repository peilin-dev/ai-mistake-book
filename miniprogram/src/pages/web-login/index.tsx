import { useEffect, useRef, useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import { useRouter } from '@tarojs/taro'
import { cancelTicket, confirmTicket, scanTicket, ticketFromScene, webLoginErrorText } from '../../lib/webLogin'
import './index.scss'

type Phase =
  | { kind: 'none' }
  | { kind: 'scanning' }
  | { kind: 'ready'; pair: string }
  | { kind: 'done'; text: string }
  | { kind: 'error'; text: string }

export default function WebLogin() {
  const { params } = useRouter()
  const ticket = ticketFromScene(params.scene)
  const [phase, setPhase] = useState<Phase>(ticket ? { kind: 'scanning' } : { kind: 'none' })
  const [busy, setBusy] = useState(false)
  const acting = useRef(false)

  useEffect(() => {
    if (!ticket) return
    scanTicket(ticket)
      .then((r) => setPhase({ kind: 'ready', pair: r.pair_code }))
      .catch((e) => setPhase({ kind: 'error', text: webLoginErrorText(e) }))
  }, [ticket])

  const act = async (fn: (t: string) => Promise<void>, doneText: string) => {
    if (!ticket || acting.current) return
    acting.current = true
    setBusy(true)
    try {
      await fn(ticket)
      setPhase({ kind: 'done', text: doneText })
    } catch (e) {
      setPhase({ kind: 'error', text: webLoginErrorText(e) })
    } finally {
      acting.current = false
      setBusy(false)
    }
  }

  return (
    <View className='page web-login'>
      {phase.kind === 'none' && <Text className='result muted'>请用微信扫电脑上的二维码</Text>}
      {phase.kind === 'scanning' && <Text className='result muted'>正在连接…</Text>}
      {phase.kind === 'error' && <Text className='result text-danger'>{phase.text}</Text>}
      {phase.kind === 'done' && <Text className='result strong'>{phase.text}</Text>}
      {phase.kind === 'ready' && (
        <View>
          <Text className='pair-code'>{phase.pair}</Text>
          <Text className='tip'>请核对电脑屏幕上的数字一致后再确认</Text>
          <View className='btn-row'>
            <Button
              className='big-btn'
              loading={busy}
              disabled={busy}
              onClick={() => void act(confirmTicket, '已登录网页版，可以回到电脑上了')}
            >
              确认登录
            </Button>
          </View>
          <Button
            className='big-btn ghost-btn'
            disabled={busy}
            onClick={() => void act(cancelTicket, '已取消')}
          >
            取消
          </Button>
        </View>
      )}
    </View>
  )
}
