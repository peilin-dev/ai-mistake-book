import { Image, ScrollView, Text, View } from '@tarojs/components'
import type { QueueItem, QueueState } from '../../lib/uploadQueue'

const LABEL: Record<QueueState, string> = {
  waiting: '等待',
  uploading: '上传中',
  done: '✓',
  failed: '失败',
  held: '未传',
  skipped: '已跳过',
}

const BAD: QueueState[] = ['failed', 'held', 'skipped']

interface Props {
  items: QueueItem[]
  /** Item currently waiting for 重试 / 跳过. */
  pausedId: string | null
  onRetry: (localId: string) => void
}

export default function ThumbStrip({ items, pausedId, onRetry }: Props) {
  if (items.length === 0) return null
  const last = items[items.length - 1]
  return (
    <ScrollView scrollX scrollIntoView={`t-${last.localId}`} style={{ whiteSpace: 'nowrap', padding: '16px 0 0' }}>
      {items.map((it, idx) => {
        const bad = BAD.includes(it.state)
        return (
          <View
            id={`t-${it.localId}`}
            key={it.localId}
            onClick={it.localId === pausedId ? () => onRetry(it.localId) : undefined}
            style={{
              display: 'inline-block',
              position: 'relative',
              width: '120px',
              height: '120px',
              marginLeft: '16px',
              border: `4px solid ${bad ? '#d93025' : 'transparent'}`,
              boxSizing: 'border-box',
            }}
          >
            <Image src={it.filePath} mode='aspectFill' style={{ width: '100%', height: '100%' }} />
            <Text
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: 0,
                textAlign: 'center',
                fontSize: '22px',
                color: '#fff',
                background: bad ? '#d93025' : 'rgba(0,0,0,0.55)',
              }}
            >
              {idx + 1} {LABEL[it.state]}
            </Text>
          </View>
        )
      })}
    </ScrollView>
  )
}
