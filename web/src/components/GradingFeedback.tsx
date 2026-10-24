import type { QuestionResult } from '../lib/results'

export function feedbackSections(q: QuestionResult): [string, string | null | undefined][] {
  const subject = q.subject || 'other'
  // Older records have no classifier: only infer writing from explicit question wording.
  const writing = q.question_type === 'writing' || (!q.question_type &&
    ['chinese', 'english'].includes(subject) && /作文|写作|习作|书面表达|write (?:an? |about)|writing/i.test(q.question_text || ''))
  const correct = q.max_score == null ? q.is_correct : q.score >= q.max_score
  if (correct && !writing && (q.question_type === 'objective' ||
    (!q.question_type && !q.is_subjective))) return []
  let sections: [string, string | null | undefined][]
  if (writing) {
    sections = [['分项评分与依据', q.scoring_basis], ['扣分依据', q.error_reason],
      [subject === 'english' ? '优秀表达' : '好句赏析', q.strengths], ['修改建议与总评', q.guidance]]
  } else if (['math', 'physics'].includes(subject)) {
    if (correct) return []
    sections = [['错因与错误步骤', q.error_reason], ['得分与扣分依据', q.scoring_basis], ['正确解法与提醒', q.guidance]]
  } else if (q.question_type === 'objective' && subject === 'english') {
    sections = [['语法与词义错因', q.error_reason], ['正确用法与解析', q.guidance]]
  } else if (subject === 'chinese' || ['history', 'geography', 'politics'].includes(subject)) {
    sections = [['得分要点', q.scoring_basis], ['遗漏要点与错误', q.error_reason], ['材料依据与答题思路', q.guidance]]
  } else if (['chemistry', 'biology', 'science'].includes(subject)) {
    sections = [['知识点与得分依据', q.scoring_basis], ['错误位置与原因', q.error_reason], ['原理、规范表达与步骤', q.guidance]]
  } else {
    sections = [['得分依据', q.scoring_basis], ['错因分析', q.error_reason], ['解答与改进建议', q.guidance]]
  }
  return sections.filter(([, content]) => !!content?.trim())
}

export default function GradingFeedback({ question: q }: { question: QuestionResult }) {
  const sections = feedbackSections(q)
  if (!sections.length) return null
  return (
    <div className="grading-feedback">
      <p className="hint">AI 批改分析 · 请结合原图核对{q.reviewed ? '；老师已复核，以下保留 AI 原始建议，分数以当前成绩为准。' : ''}</p>
      {sections.map(([title, content]) => (
        <section key={title}>
          <h4>{title}</h4>
          <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{content}</p>
        </section>
      ))}
    </div>
  )
}
