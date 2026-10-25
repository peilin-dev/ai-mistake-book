import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { errorText, request } from '../lib/api'
import { useLeaveGuard } from '../lib/useLeaveGuard'

interface ClaimPage { page_id: number; seq: number; recognized_name: string | null; question_nos: string[]; image_url: string | null; suggested_student_id: number | null }
interface ClaimStudent { id: number; name: string; student_no: string | null }
interface Queue { pages: ClaimPage[]; students: ClaimStudent[] }
export default function BatchClaims({ assignmentId }: { assignmentId: string }) {
  const [data, setData] = useState<Queue>(), [selected, setSelected] = useState<number[]>([])
  const [targets, setTargets] = useState<Record<number, number>>({}), [error, setError] = useState('')
  const [notice, setNotice] = useState(''), [busy, setBusy] = useState(false), [reload, setReload] = useState(0)
  const lock = useRef(false)
  useLeaveGuard(busy || selected.length > 0, '还有未确认的试卷归属，确定离开吗？')
  useEffect(() => {
    let live = true
    setData(undefined); setSelected([]); setTargets({}); setError('')
    request<Queue>('GET', `/api/assignments/${assignmentId}/claims`).then(queue => {
      if (!live) return
      if (!Array.isArray(queue.pages) || !Array.isArray(queue.students)) throw new Error('暂时无法读取试卷归属列表')
      setData(queue); setSelected([]); setTargets({}); setError('')
    }).catch(e => live && setError(errorText(e)))
    return () => { live = false }
  }, [assignmentId, reload])
  const options = <><option value="">选择学生</option>{data?.students.map(s => <option key={s.id} value={s.id} disabled={!s.student_no && data.students.filter(other => other.name === s.name).length > 1}>{s.name}{s.student_no ? ` · 学号 ${s.student_no}` : data.students.filter(other => other.name === s.name).length > 1 ? ' · 同名，请先补充学号' : ''}</option>)}</>
  const missing = selected.filter(id => !targets[id]).length
  return <section className="batch-claims" aria-label="批量归属">
    {notice && <p role="status" className="notice">{notice}</p>}
    {error && <p role="alert" className="err">{error} <button disabled={busy} onClick={() => setReload(n => n + 1)}>刷新待归属页</button></p>}
    {!data && !error && <p className="empty">正在读取待归属卷子…</p>}
    {data?.pages.length === 0 && <div className="empty"><h2>无需手动归属</h2><p>已完成的卷子都已匹配学生。姓名或学号明确的卷子会自动归属，仅异常页需要处理。</p><Link to={`/a/${assignmentId}/grades`}>查看成绩与原卷</Link></div>}
    {!!data?.pages.length && <>
      <p>还有 <strong>{data.pages.length}</strong> 页待归属。先勾选同一学生的卷子，再统一选学生；也可逐行指定不同学生，一次确认。</p>
      <div className="batch-claim-toolbar">
        <label><input type="checkbox" disabled={busy} checked={data.pages.slice(0, 200).every(p => selected.includes(p.page_id))} onChange={e => setSelected(e.target.checked ? data.pages.slice(0, 200).map(p => p.page_id) : [])} />{data.pages.length > 200 ? '选择前 200 页' : '全选待归属页'}</label>
        <label>已选 {selected.length} 页，统一归属到<select aria-label="统一归属到学生" disabled={busy || !selected.length} value="" onChange={e => { const sid = Number(e.target.value); if (sid) setTargets(old => ({ ...old, ...Object.fromEntries(selected.map(id => [id, sid])) })) }}>{options}</select></label>
        <button disabled={busy || !data.pages.some(p => p.suggested_student_id)} onClick={() => {
          const suggested = data.pages.filter(p => p.suggested_student_id).slice(0, 200)
          setSelected(suggested.map(p => p.page_id)); setTargets(old => ({ ...old, ...Object.fromEntries(suggested.map(p => [p.page_id, p.suggested_student_id!])) }))
        }}>选中姓名一致的建议</button>
      </div>
      <div className="table-scroll"><table className="work-table batch-claim-table"><thead><tr><th>选择</th><th>原卷</th><th>识别结果</th><th>归属学生</th></tr></thead><tbody>{data.pages.map(p => <tr key={p.page_id} className={selected.includes(p.page_id) ? 'claim-selected' : ''}>
        <td><input type="checkbox" aria-label={`选择第 ${p.seq} 页`} checked={selected.includes(p.page_id)} disabled={busy || selected.length >= 200 && !selected.includes(p.page_id)} onChange={e => setSelected(old => e.target.checked ? [...old, p.page_id] : old.filter(id => id !== p.page_id))} /></td>
        <td>{p.image_url ? <a href={p.image_url} target="_blank" rel="noreferrer"><img className="claim-batch-thumb" src={p.image_url} alt={`第 ${p.seq} 页原卷`} loading="lazy" /></a> : <span className="hint">原图不可用</span>}<p>第 {p.seq} 页</p></td>
        <td><strong>{p.recognized_name || '未识别姓名'}</strong><p className="hint">题号 {p.question_nos.join('、') || '未识别'}</p>{p.suggested_student_id && <span className="hint">与名单姓名一致，请对照原图确认</span>}</td>
        <td><select aria-label={`第 ${p.seq} 页归属学生`} disabled={busy || selected.length >= 200 && !selected.includes(p.page_id)} value={targets[p.page_id] || ''} onChange={e => { const sid = Number(e.target.value); setTargets(old => ({ ...old, [p.page_id]: sid })); setSelected(old => sid ? [...new Set([...old, p.page_id])] : old.filter(id => id !== p.page_id)) }}>{options}</select></td>
      </tr>)}</tbody></table></div>
      <div className="batch-claim-submit"><div><strong>已选 {selected.length} 页</strong><span className="hint">{missing ? ` · 还有 ${missing} 页未选择学生` : ' · 请核对原图与归属后确认'}</span></div><button className="btn-primary" disabled={busy || !selected.length || missing > 0} onClick={async () => {
        if (lock.current) return
        lock.current = true; setBusy(true); setError(''); setNotice('')
        try {
          const result = await request<{ assigned: number }>('POST', `/api/assignments/${assignmentId}/claims`, { assignments: selected.map(page_id => ({ page_id, student_id: targets[page_id] })) })
          setNotice(`已确认 ${result.assigned} 页归属，成绩已更新。`); setReload(n => n + 1)
        } catch (e) { setError(errorText(e)) }
        finally { lock.current = false; setBusy(false) }
      }}>{busy ? '正在更新归属…' : `确认 ${selected.length} 页归属`}</button></div>
      <p className="hint">每批最多确认 200 页。不会按图片顺序猜测学生；同一学生出现重复题号会提示核对。同名学生请先在班级名单补充学号。</p>
    </>}
  </section>
}
