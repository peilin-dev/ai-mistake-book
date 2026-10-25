import { Link } from 'react-router-dom'
import Icon from './Icon'

export default function WorkflowSteps({ assignmentId, current, unclaimed = 0 }: { assignmentId: number | string; current: number; unclaimed?: number }) {
  const steps = [
    { label: '上传卷子', path: 'upload', icon: 'upload' as const },
    { label: 'AI 批改', path: 'work', icon: 'pen' as const },
    { label: '认领与复核', path: unclaimed ? 'claim' : 'review', icon: 'clipboard' as const },
    { label: '原卷与成绩', path: 'grades', icon: 'chart' as const },
  ]
  return <nav className="workflow-steps" aria-label="批改流程"><ol>{steps.map((step, index) => <li key={step.label} className={index === current ? 'is-current' : index < current ? 'is-complete' : ''}>
    <Link to={`/a/${assignmentId}/${step.path}`} aria-current={index === current ? 'step' : undefined}>
      <span className="workflow-step-icon"><Icon name={index < current ? 'check' : step.icon} size={17} /></span><span>{step.label}</span>
    </Link>
  </li>)}</ol></nav>
}
