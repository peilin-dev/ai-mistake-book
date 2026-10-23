/** Development-only visual review entry. Not included in Vite's production entry graph. */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { MemoryRouter, NavLink, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import Overview from './pages/Overview'
import Question from './pages/Question'
import Downloads from './pages/Downloads'
import Login from './pages/Login'
import ClassNew from './pages/ClassNew'
import ClassDetail from './pages/ClassDetail'
import './theme.css'
import './preview.css'

const classes = [
  { id: 1, name: '五年级一班', grade: 5 },
  { id: 2, name: '五年级二班', grade: 5 },
  { id: 3, name: '六年级一班', grade: 6 },
]
const assignments = [
  { id: 6, class_id: 1, title: '小数乘法 · 单元巩固练习', subject: 'math', created_at: '2026-10-23T01:00:00Z' },
  { id: 5, class_id: 1, title: '第三周阅读理解', subject: 'chinese', created_at: '2026-10-22T01:00:00Z' },
  { id: 4, class_id: 1, title: 'Unit 3 · What would you like?', subject: 'english', created_at: '2026-10-21T01:00:00Z' },
  { id: 3, class_id: 1, title: '小数除法 · 课堂练习', subject: 'math', created_at: '2026-10-20T01:00:00Z' },
  { id: 2, class_id: 1, title: '语文园地二 · 积累与运用', subject: 'chinese', created_at: '2026-10-19T01:00:00Z' },
  { id: 1, class_id: 1, title: '第一单元综合练习', subject: 'math', created_at: '2026-10-16T01:00:00Z' },
]
const knowledge = ['小数乘整数', '积的小数位数', '小数乘小数', '积的近似数', '整数乘法运算律']
const wrong = [3, 5, 18, 7, 2, 21, 9, 4, 15, 6, 1, 12, 8, 3, 17]
const analytics = {
  counted_students: 40, roster_size: 42, average_score: 83.5, average_ratio: .835, pass_rate: .925,
  pending_review: 3, pages_not_counted: 2,
  questions: wrong.map((n, i) => ({ question_no: String(i + 1), knowledge_point: knowledge[i % 5], wrong_count: n, student_count: 40, answered_count: 40, accuracy: (40 - n) / 40, top_wrong_answer: null, is_subjective: false })),
}
const students = ['示例学生甲', '示例学生乙', '示例学生丙', '示例学生丁', '示例学生戊', '示例学生己'].map((name, i) => ({ id: i + 1, name, student_no: i === 2 ? null : String(i + 1).padStart(2, '0') }))
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

if (import.meta.env.DEV) {
  // No fallback to native fetch: preview actions never reach a real server.
  window.fetch = async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.origin)
    const p = url.pathname
    if (p === '/api/me') return response({ id: 1, display_name: '林老师', last_subject: 'math' })
    if (p === '/api/classes' && init?.method === 'POST') return response({ id: 1, name: '示例班级', grade: 5 }, 201)
    if (p === '/api/classes') return response(classes)
    if (/^\/api\/classes\/\d+\/students$/.test(p)) return response(students)
    if (/^\/api\/classes\/\d+\/students:import$/.test(p)) return response({ created: 2, students })
    if (/^\/api\/students\/\d+$/.test(p) && init?.method === 'PATCH') return response({ ...students[0], ...JSON.parse(String(init.body)) })
    if (/^\/api\/(students|classes)\/\d+$/.test(p) && init?.method === 'DELETE') return new Response(null, { status: 204 })
    const classMatch = p.match(/^\/api\/classes\/(\d+)\/assignments$/)
    if (classMatch) return response(classMatch[1] === '3' ? [] : assignments.map(a => ({ ...a, class_id: Number(classMatch[1]) })))
    if (p.endsWith('/analytics')) return response(analytics)
    if (p.endsWith('/causes')) return response({ causes: { a: '计算时没有正确确定积的小数位数，建议先估算结果的范围。', b: '把小数乘法当作加法处理，需要重新理解运算的意义。' } })
    const q = p.match(/\/analytics\/questions\/(\d+)$/)
    if (q) { const i = Number(q[1]) - 1; const n = wrong[i] ?? 3; const a = Math.ceil(n * .65); return response({ question_no: q[1], question_text: '计算：2.4 × 0.3', correct_answer: '0.72', is_subjective: false, knowledge_point: knowledge[i % 5], wrong_count: n, student_count: 40, answered_count: 40, groups: [{ key: 'a', answer: '7.2', count: a, students: [] }, { key: 'b', answer: '2.7', count: n - a, students: [] }], score_buckets: [], crops: [] }) }
    const assignment = p.match(/^\/api\/assignments\/(\d+)$/)
    if (assignment) return response(assignments.find(a => a.id === Number(assignment[1])) ?? assignments[0])
    if (p.endsWith('/practice')) return response({ status: 'ready' })
    if (init?.method === 'POST' && p.endsWith('/exports')) return response({ detail: '当前为界面预览，不生成真实 PDF。正式页面将使用实际作业数据导出。' }, 409)
    return response({ detail: '此操作不在界面预览范围内' }, 400)
  }
}

function Preview() {
  return <MemoryRouter><div className="preview-bar"><span><strong>第一版预览</strong><span className="preview-note">示例数据 · 不影响真实班级</span></span><nav aria-label="预览页面"><NavLink to="/" end>班级作业</NavLink><NavLink to="/a/6" end>学情概览</NavLink><NavLink to="/a/6/q/3">课堂讲评</NavLink><NavLink to="/a/6/downloads">下载打印</NavLink><NavLink to="/classes/new">新建班级</NavLink><NavLink to="/classes/1">班级管理</NavLink><NavLink to="/login">登录页</NavLink></nav></div><Routes><Route path="/" element={<Home />} /><Route path="/a/:assignmentId" element={<Overview />} /><Route path="/a/:assignmentId/q/:questionNo" element={<Question />} /><Route path="/a/:assignmentId/downloads" element={<Downloads />} /><Route path="/classes/new" element={<ClassNew />} /><Route path="/classes/:classId" element={<ClassDetail />} /><Route path="/login" element={<Login previewOnly />} /></Routes></MemoryRouter>
}

if (import.meta.env.DEV) ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Preview /></React.StrictMode>)
