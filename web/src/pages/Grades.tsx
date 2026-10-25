import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import { errorText, request } from '../lib/api'
import type { Submission } from '../lib/results'
export default function Grades() {
  const { assignmentId } = useParams()
  const [list, setList] = useState<Submission[] | null>(null),
    [error, setError] = useState(''),
    [query, setQuery] = useState(''),
    [order, setOrder] = useState('name'),
    [missing, setMissing] = useState<string[]>([])
  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        const [submissions, a] = await Promise.all([
          request<Submission[]>(
            'GET',
            `/api/assignments/${assignmentId}/submissions`,
          ),
          request<{ class_id: number }>(
            'GET',
            `/api/assignments/${assignmentId}`,
          ),
        ])
        const students = await request<{ id: number; name: string }[]>(
          'GET',
          `/api/classes/${a.class_id}/students`,
        )
        if (live) {
          setList(submissions)
          const ids = new Set(submissions.map((s) => s.student_id))
          setMissing(students.filter((s) => !ids.has(s.id)).map((s) => s.name))
        }
      } catch (e) {
        if (live) setError(errorText(e))
      }
    })()
    return () => {
      live = false
    }
  }, [assignmentId])
  const visible = list
    ?.filter((s) => s.student_name.includes(query.trim()))
    .sort((a, b) =>
      order === 'score'
        ? b.total_score - a.total_score || a.id - b.id
        : a.student_name.localeCompare(b.student_name, 'zh-CN'),
    )
  return (
    <WorkShell
      title="作业成绩"
      description="含学生姓名，请在教师个人电脑上查看。未认领的页不计入学生成绩。"
    >
      {error && (
        <p role="alert" className="err">
          {error}
        </p>
      )}
      <div className="section-heading">
        <label>
          查找学生
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label>
          排序
          <select value={order} onChange={(e) => setOrder(e.target.value)}>
            <option value="name">姓名</option>
            <option value="score">分数从高到低</option>
          </select>
        </label>
      </div>
      {list === null && !error && <p className="empty">加载中…</p>}
      {list && (
        <div className="table-scroll">
          <table className="work-table">
            <thead>
              <tr>
                <th>学生</th>
                <th>总分</th>
                <th>待复核</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              {visible?.map((s) => (
                <tr key={s.id}>
                  <td>{s.student_name}</td>
                  <td>{s.total_score}</td>
                  <td>{s.needs_review_count} 项</td>
                  <td>
                    <Link to={`/a/${assignmentId}/students/${s.id}`}>
                      查看原卷与 AI 批改
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visible?.length === 0 && (
            <p className="empty">
              {list.length ? '没有找到这位学生' : '还没有已归属的成绩'}
            </p>
          )}
        </div>
      )}
      {missing.length > 0 && (
        <section className="notice">
          <h2>尚无成绩的学生（{missing.length} 人）</h2>
          <p>{missing.join('、')}</p>
          <p>
            可能还未上传、尚在批改或等待认领。
            <Link to={`/a/${assignmentId}/work`}>查看批改进度</Link>
          </p>
        </section>
      )}
    </WorkShell>
  )
}
