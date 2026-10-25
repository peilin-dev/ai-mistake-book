import type { IconName } from '../components/Icon'

export const workNav: { path: string; label: string; icon: IconName }[] = [
  { path: 'work', label: '批改进度', icon: 'layers' },
  { path: 'answer-key', label: '答案卷', icon: 'file' },
  { path: 'upload', label: '上传卷子', icon: 'upload' },
  { path: 'claim', label: '待认领', icon: 'users' },
  { path: 'review', label: '复核', icon: 'clipboard' },
  { path: 'grades', label: '成绩', icon: 'chart' },
  { path: 'practice', label: '练习卷', icon: 'pen' },
  { path: '', label: '学情', icon: 'book' },
  { path: 'downloads', label: '下载打印', icon: 'print' },
]

export function workPath(assignmentId: string, path: string) {
  return `/a/${assignmentId}${path ? '/' + path : ''}`
}
