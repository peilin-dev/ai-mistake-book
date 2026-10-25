import type { QuestionResult } from '../lib/results'

export default function ScoreBreakdown({ question }: { question: QuestionResult }) {
  if (!question.scoring_steps?.length) return null
  const steps = question.scoring_steps
  return <section className="score-breakdown" aria-label="步骤得分">
    <div className="section-heading"><h3>步骤得分</h3><span>AI 初始评分 {steps.reduce((sum, step) => sum + step.score, 0)} / {steps.reduce((sum, step) => sum + step.max_score, 0)}</span></div>
    {question.reviewed && <p className="hint">老师已复核，以下为 AI 原始步骤评分；最终成绩以当前得分为准。</p>}
    <ol>{steps.map((step, index) => <li key={index}><div><strong>{step.criterion}</strong><span className={step.score < step.max_score ? 'step-lost' : 'step-earned'}>{step.score} / {step.max_score} 分</span></div><p>{step.reason}</p></li>)}</ol>
  </section>
}
