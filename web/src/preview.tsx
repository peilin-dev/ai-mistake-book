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
import AssignmentNew from './pages/AssignmentNew'
import AssignmentWork from './pages/AssignmentWork'
import Upload from './pages/Upload'
import Claim from './pages/Claim'
import AnswerKey from './pages/AnswerKey'
import Review from './pages/Review'
import Grades from './pages/Grades'
import Student from './pages/Student'
import Practice from './pages/Practice'
import type { PageItem } from './lib/pages'
import './theme.css'
import './workspace.css'
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

let previewName = '林老师'
let samplePages: PageItem[] = [
  { page_id:1,seq:1,status:'done',fail_reason:null,student_id:1,student_name:'示例学生甲',recognized_name:'示例学生甲',source:'web' },
  { page_id:2,seq:2,status:'done',fail_reason:null,student_id:null,student_name:null,recognized_name:null,source:'web' },
  { page_id:3,seq:3,status:'failed',fail_reason:'model_unavailable',student_id:null,student_name:null,recognized_name:null,source:'web' },
]
const sampleQuestion = {subject:'math',question_type:'calculation',error_reason:'小数位数判断错误：两个因数共两位小数，学生将积写成 7.2，小数点应再向左移动一位。',scoring_basis:'AI建议评分细则，待老师确认：整数乘法2分，小数点位置3分；合计2/5分。',guidance:'先算 24 × 3 = 72，再从右往左数两位点上小数点，得到 0.72。估算时，2.4 的三成应小于 2.4，可用于检查结果。',id:1,page_id:1,question_no:'3',question_text:'计算：2.4 × 0.3',student_answer:'7.2',correct_answer:'0.72',is_correct:false,score:2,max_score:5,crop_url:null,image_url:'/tests/fixtures/comparison-example.svg',scoring_steps:[{criterion:'整数乘法',score:2,max_score:2,reason:'24 × 3 = 72，整数乘法正确。'},{criterion:'小数点位置',score:0,max_score:3,reason:'两个因数共两位小数，积应为 0.72。'}],student_name:'示例学生甲',reason:'answer_mismatch',needs_review:true,reviewed:false}
let sampleQuestions = [sampleQuestion]
let sampleAnswerKey = {answer_key_status:'confirmed',items:[{question_no:'1',answer:'0.72',max_score:5,is_subjective:false},{question_no:'2',answer:'3.6',max_score:5,is_subjective:false}]}

if (import.meta.env.DEV) {
  // No fallback to native fetch: preview actions never reach a real server.
  window.fetch = async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.origin)
    const p = url.pathname
    if (p === '/api/assignments' && init?.method === 'POST') return response({ ...assignments[0],id:6 },201)
    if (p.endsWith('/progress')) return response({total:samplePages.length,queued:0,processing:0,done:samplePages.filter(p => p.status === 'done').length,failed:samplePages.filter(p => p.status === 'failed').length,needs_review:sampleQuestions.length})
    if (p.endsWith('/pages') && init?.method === 'GET') return response(samplePages)
    if (p.endsWith('/review')) return response({pages_unassigned:samplePages.filter(p => p.status === 'done' && p.student_id === null),questions:sampleQuestions})
    if (p.endsWith('/claims')) {
      if (init?.method === 'POST') {
        const rows = JSON.parse(String(init.body)).assignments as {page_id:number; student_id:number}[]
        samplePages = samplePages.map(page => { const row = rows.find(r => r.page_id === page.page_id); return row ? {...page, student_id:row.student_id, student_name:students.find(s=>s.id===row.student_id)?.name || null} : page })
        return response({assigned:rows.length})
      }
      return response({pages:samplePages.filter(page=>page.status==='done' && page.student_id===null).map(page=>({...page, image_url:'/tests/fixtures/comparison-example.svg',question_nos:['3'],suggested_student_id:null})),students:students.map(s=>({...s,student_no:s.student_no}))})
    }
    if (p.endsWith('/claim-candidates')) return response({page_id:2,image_url:null,question_nos:['4','5'],candidates:students.map(s => ({student_id:s.id,name:s.name,missing_all:true,page_count:1,thumb_url:null}))})
    if (/^\/api\/pages\/\d+$/.test(p) && init?.method === 'PATCH') { samplePages = samplePages.filter(r => r.page_id !== 2); return response({page_id:2,student_id:1}) }
    if (/^\/api\/pages\/\d+$/.test(p) && init?.method === 'DELETE') { samplePages = samplePages.filter(r => r.page_id !== Number(p.split('/').pop())); return new Response(null,{status:204}) }
    if (p.endsWith(':retry')) return response({page_id:3,status:'queued'})
    if (/^\/api\/question-results\/\d+$/.test(p) && init?.method === 'PATCH') { sampleQuestions = []; return response({...sampleQuestion,...JSON.parse(String(init.body)),reviewed:true,needs_review:false}) }
    if (p.endsWith('/grading-rules')) return response({ ...assignments[0], grading_rules: JSON.parse(String(init?.body)).grading_rules })
    if (p.endsWith('/answer-key')) {
      if (init?.method === 'DELETE') sampleAnswerKey = {answer_key_status:'none',items:[]}
      if (init?.method === 'PUT') sampleAnswerKey = {answer_key_status:'confirmed',items:JSON.parse(String(init.body)).items}
      return response({...sampleAnswerKey,regrade_suggested:true})
    }
    if (p.endsWith('/submissions')) return response(students.slice(0,4).map((s,i) => ({id:s.id,student_id:s.id,student_name:s.name,total_score:85+i*3,needs_review_count:i===0?1:0})))
    if (p.endsWith('/history')) return response(assignments.slice(0,4).map((a,i) => ({assignment_id:a.id,title:a.title,score:85-i*4,max_score:100,ratio:(85-i*4)/100})))
    if (p.endsWith('/summary')) return response({summary:'示例小结：小数位数的判断还需巩固，建议先估算结果，再检查积的小数点位置。'})
    if (/^\/api\/submissions\/\d+$/.test(p)) return response({id:1,student_id:1,student_name:'示例学生甲',total_score:85,needs_review_count:1,questions:[sampleQuestion]})
    if (p === '/api/me') {
      if (init?.method === 'PATCH') previewName = JSON.parse(String(init.body)).display_name.trim()
      return response({ id: 1, display_name: previewName, last_subject: 'math', login_name: null, quota_total: 100, quota_used: 37 })
    }
    if (p === '/api/classes' && init?.method === 'POST') return response({ id: 1, name: '示例班级', grade: 5 }, 201)
    if (p === '/api/classes') return response(classes)
    if (/^\/api\/classes\/\d+\/students$/.test(p)) return response(students)
    if (/^\/api\/classes\/\d+\/students:import$/.test(p)) return response({ created: 2, students })
    if (/^\/api\/students\/\d+$/.test(p) && init?.method === 'PATCH') return response({ ...students[0], ...JSON.parse(String(init.body)) })
    if (/^\/api\/(students|classes)\/\d+$/.test(p) && init?.method === 'DELETE') return new Response(null, { status: 204 })
    const classMatch = p.match(/^\/api\/classes\/(\d+)\/assignments$/)
    if (classMatch) return response(classMatch[1] === '3' ? [] : assignments.map(a => ({ ...a, class_id: Number(classMatch[1]), answer_key_status: a.id % 2 ? 'none' : 'confirmed' })))
    if (p.endsWith('/analytics')) return response(analytics)
    if (p.endsWith('/causes')) return response({ causes: { a: '计算时没有正确确定积的小数位数，建议先估算结果的范围。', b: '把小数乘法当作加法处理，需要重新理解运算的意义。' } })
    const q = p.match(/\/analytics\/questions\/(\d+)$/)
    if (q) { const i = Number(q[1]) - 1; const n = wrong[i] ?? 3; const a = Math.ceil(n * .65); return response({ question_no: q[1], question_text: '计算：2.4 × 0.3', correct_answer: '0.72', is_subjective: false, knowledge_point: knowledge[i % 5], wrong_count: n, student_count: 40, answered_count: 40, groups: [{ key: 'a', answer: '7.2', count: a, students: [] }, { key: 'b', answer: '2.7', count: n - a, students: [] }], score_buckets: [], crops: [] }) }
    const assignment = p.match(/^\/api\/assignments\/(\d+)$/)
    if (assignment) return response(assignments.find(a => a.id === Number(assignment[1])) ?? assignments[0])
    if (p.endsWith('/practice')) return response({ id:1,status:'done',student_name:null,partial:false,sources_total:2,sources_done:2,error:null,last_replace_failed_item:null,items:[{id:1,position:1,source_no:'3',knowledge_point:'小数乘小数',stem:'计算：1.6 × 0.4，并说一说你是怎样确定积的小数位数的。',options:null,answer:'0.64',replacing:false},{id:2,position:2,source_no:'6',knowledge_point:'积的近似数',stem:'一个长方形的长是 2.8 米，宽是 1.5 米，它的面积是多少平方米？',options:null,answer:'4.2 平方米',replacing:false}] })
    if (init?.method === 'POST' && p.endsWith('/exports')) return response({ detail: '当前为界面预览，不生成真实 PDF。正式页面将使用实际作业数据导出。' }, 409)
    return response({ detail: '此操作不在界面预览范围内' }, 400)
  }
}

function Preview() {
  return <MemoryRouter><div className="preview-bar"><span><strong>第一版预览</strong><span className="preview-note">示例数据 · 不影响真实班级</span></span><nav aria-label="预览页面"><NavLink to="/" end>班级作业</NavLink><NavLink to="/a/6/work">作业处理</NavLink><NavLink to="/a/6" end>学情概览</NavLink><NavLink to="/a/6/q/3">课堂讲评</NavLink><NavLink to="/a/6/downloads">下载打印</NavLink><NavLink to="/classes/new">新建班级</NavLink><NavLink to="/classes/1">班级管理</NavLink><NavLink to="/login">登录页</NavLink></nav></div><Routes><Route path="/classes/:classId/assignments/new" element={<AssignmentNew />} /><Route path="/a/:assignmentId/work" element={<AssignmentWork />} /><Route path="/a/:assignmentId/upload" element={<Upload />} /><Route path="/a/:assignmentId/claim" element={<Claim />} /><Route path="/a/:assignmentId/answer-key" element={<AnswerKey />} /><Route path="/a/:assignmentId/review" element={<Review />} /><Route path="/a/:assignmentId/grades" element={<Grades />} /><Route path="/a/:assignmentId/students/:submissionId" element={<Student />} /><Route path="/a/:assignmentId/practice" element={<Practice />} /><Route path="/a/:assignmentId/students/:submissionId/practice" element={<Practice />} /><Route path="/" element={<Home />} /><Route path="/a/:assignmentId" element={<Overview />} /><Route path="/a/:assignmentId/q/:questionNo" element={<Question />} /><Route path="/a/:assignmentId/downloads" element={<Downloads />} /><Route path="/classes/new" element={<ClassNew />} /><Route path="/classes/:classId" element={<ClassDetail />} /><Route path="/login" element={<Login previewOnly />} /></Routes></MemoryRouter>
}

if (import.meta.env.DEV) ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Preview /></React.StrictMode>)
