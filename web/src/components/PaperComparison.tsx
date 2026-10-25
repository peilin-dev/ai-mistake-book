import { useState } from 'react'
import type { QuestionResult } from '../lib/results'
import GradingFeedback from './GradingFeedback'
import ResultEditor from './ResultEditor'

export interface PaperPage { page_id: number; seq: number; image_url: string | null; status?: string }
export default function PaperComparison({ questions, pages, onSaved }: {
  questions: QuestionResult[]; pages?: PaperPage[]; onSaved: () => Promise<void>
}) {
  const sourcePages = pages?.length ? pages : Array.from(new Map(questions.map(q => [q.page_id, { page_id: q.page_id, seq: 0, image_url: q.image_url || null }])).values()).map((p, i) => ({ ...p, seq: i + 1 }))
  const [pageId, setPageId] = useState<number>(), [questionId, setQuestionId] = useState<number>()
  const [zoom, setZoom] = useState(100), [crop, setCrop] = useState(false)
  const [editing, setEditing] = useState(false), [failedUrl, setFailedUrl] = useState('')
  const page = sourcePages.find(p => p.page_id === pageId) || sourcePages[0]
  const pageQuestions = questions.filter(q => q.page_id === page?.page_id)
  const q = pageQuestions.find(q => q.id === questionId) || pageQuestions[0]
  const url = (crop && q?.crop_url ? q.crop_url : page?.image_url) || ''
  return <section className="paper-comparison" aria-label="原卷与 AI 批改对照">
    <div className="paper-pane">
      <div className="paper-controls">
        <label>原卷<select aria-label="选择原卷页" value={page?.page_id ?? ''} onChange={e => { setPageId(Number(e.target.value)); setEditing(false); setZoom(100); setCrop(false) }}>
          {sourcePages.map(p => <option key={p.page_id} value={p.page_id}>第 {p.seq} 页</option>)}
        </select></label>
        <button disabled={zoom <= 75} onClick={() => setZoom(z => z - 25)} aria-label="缩小原卷">−</button>
        <span>{zoom}%</span><button disabled={zoom >= 250} onClick={() => setZoom(z => z + 25)} aria-label="放大原卷">＋</button>
        {q?.crop_url && <button onClick={() => setCrop(v => !v)}>{crop ? '查看整页' : '只看本题'}</button>}
        {url && <a href={url} target="_blank" rel="noreferrer">打开原图</a>}
      </div>
      <div className="paper-image-viewport">
        {url && failedUrl !== url ? <img src={url} style={{ width: `${zoom}%`, maxWidth: 'none' }} alt={crop ? `第 ${q?.question_no} 题原始作答` : `第 ${page?.seq} 页原卷`} onError={() => setFailedUrl(url)} /> : <p className="empty">{url ? '图片暂时无法加载，请刷新页面重试。' : '此页原卷暂不可用，可能已超过图片保留期限。'}</p>}
      </div>
    </div>
    <div className="paper-result-pane">
      <h2>AI 批改对照</h2>
      <nav className="question-picker" aria-label="选择题目">{pageQuestions.map(item => <button key={item.id} aria-pressed={q?.id === item.id} onClick={() => { setQuestionId(item.id); setEditing(false) }}>第 {item.question_no} 题 · {item.score}/{item.max_score ?? '—'}</button>)}</nav>
      {!q && <p className="empty">这一页还没有批改结果，请稍后到批改进度查看。</p>}
      {q && <article key={q.id}>
        <div className="section-heading"><h3>第 {q.question_no} 题 · {q.is_correct ? '正确' : q.score > 0 && q.max_score !== null && q.score < q.max_score ? '部分得分' : q.is_subjective ? '评分' : '错误'}</h3><strong>{q.score} / {q.max_score ?? '未标分值'}</strong></div>
        {q.reviewed && <p className="hint">老师已复核{q.model_score != null ? ` · AI 原始得分 ${q.model_score}` : ''}，当前显示最终成绩。</p>}
        {q.needs_review && !q.reviewed && <p className="notice">此题需老师复核</p>}
        <p>{q.question_text}</p>
        <h4>识别出的学生作答</h4><p className="answer-text">{q.student_answer || '未识别，请对照原卷核实'}</p>
        <h4>参考答案 / 评分要求</h4><p className="answer-text">{q.correct_answer || '未提供'}</p>
        <GradingFeedback question={q} />
        <button onClick={() => setEditing(v => !v)}>{editing ? '收起修改' : '修改判定'}</button>
        {editing && <ResultEditor question={q} onSaved={async () => { await onSaved(); setEditing(false) }} />}
      </article>}
    </div>
  </section>
}
