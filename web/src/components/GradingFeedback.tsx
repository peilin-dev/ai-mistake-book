import type { QuestionResult } from '../lib/results'

export default function GradingFeedback({ question: q }: { question: QuestionResult }) {
  const sections = [
    ['评分依据', q.scoring_basis],
    ['错因与扣分说明', q.error_reason],
    ['好句与作答亮点', q.strengths],
    ['解题思路与修改建议', q.guidance],
  ]
  return (
    <div className="grading-feedback">
      <p className="hint">AI 批改指导 · 请结合原图核对{q.reviewed ? '；老师已复核，以下保留 AI 原始建议，分数以当前成绩为准。' : ''}</p>
      {sections.map(([title, content]) => (
        <section key={title}>
          <h4>{title}</h4>
          <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {content || (title === '错因与扣分说明' && q.max_score !== null && q.score >= q.max_score
              ? '本题未扣分。'
              : title === '好句与作答亮点'
                ? '本次未记录可确认的好句或作答亮点。'
                : '本次批改未记录此项指导；旧记录不会自动补写。')}
          </p>
        </section>
      ))}
    </div>
  )
}
