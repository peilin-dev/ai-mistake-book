import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import Icon from '../components/Icon'
import { request, errorText } from '../lib/api'
import { subjectsForGrade } from '../lib/subjects'
import { gradingRules } from '../lib/gradingRules'
import { ACCEPT } from '../lib/intake'
import { stageAssignmentMaterials } from '../lib/assignmentMaterials'
import type { ClassOut } from '../lib/overview'
import type { MeInfo } from '../lib/me'

export default function AssignmentNew() {
  const { classId } = useParams(), navigate = useNavigate()
  const [rooms, setRooms] = useState<ClassOut[]>([]), [room, setRoom] = useState<ClassOut>()
  const [title, setTitle] = useState(''), [subject, setSubject] = useState('math')
  const [rules, setRules] = useState(''), [files, setFiles] = useState<File[]>([])
  const [material, setMaterial] = useState('answer-key'), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const lock = useRef(false)
  useEffect(() => {
    let live = true
    Promise.all([request<ClassOut[]>('GET', '/api/classes'), request<MeInfo>('GET', '/api/me')])
      .then(([classes, me]) => {
        if (!live) return
        setRooms(classes)
        const found = classes.find(c => c.id === Number(classId))
        if (!found) { setError('找不到这个班级'); return }
        setRoom(found)
        setSubject(subjectsForGrade(found.grade).some(s => s.value === me.last_subject) ? me.last_subject! : 'math')
      }).catch(e => live && setError(errorText(e)))
    return () => { live = false }
  }, [classId])
  function addFiles(next: File[]) { setFiles(old => [...old, ...next]); setError('') }
  return <WorkShell title="新建作业" description="选好班级，填入作业信息；可提前选好材料，创建后继续核对或上传。">
    <div className="assignment-create-layout">
      <form className="assignment-create-form" onSubmit={async e => {
        e.preventDefault()
        if (lock.current || !title.trim() || !room) return
        lock.current = true; setBusy(true); setError('')
        try {
          const a = await request<{ id: number }>('POST', '/api/assignments', { class_id: room.id, title: title.trim(), subject, ...(rules.trim() ? { grading_rules: rules.trim() } : {}) })
          if (files.length) stageAssignmentMaterials(a.id, files)
          navigate(`/a/${a.id}/${files.length ? material : 'work'}`)
        } catch (e) { setError(errorText(e)); lock.current = false; setBusy(false) }
      }}>
        <fieldset disabled={busy}>
          <legend>作业信息</legend>
          <div className="creation-fields">
            <label>学科<select required disabled={!room} value={subject} onChange={e => setSubject(e.target.value)} aria-describedby="subject-grade-hint">{subjectsForGrade(room?.grade ?? 1).map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
            <label>布置到班级<select required aria-label="布置到班级" disabled={!rooms.length} value={room?.id ?? ''} onChange={e => {
              const next = rooms.find(c => c.id === Number(e.target.value))
              setRoom(next)
              if (next && !subjectsForGrade(next.grade).some(s => s.value === subject)) setSubject('math')
            }}>{rooms.map(c => <option key={c.id} value={c.id}>{c.name} · {c.grade} 年级</option>)}</select></label>
          </div>
          <p id="subject-grade-hint" className="hint">{room ? `${room.grade >= 7 ? '初中' : '小学'} ${room.grade} 年级，学科按年级显示。` : '正在读取班级…'}</p>
          <label>作业名称<input required maxLength={64} value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：九年级数学 · 二次函数单元练习" /></label>
        </fieldset>
        <fieldset disabled={busy} className="creation-materials">
          <legend>添加材料 <span className="hint">可选，创建后也能上传</span></legend>
          <div className="material-types" role="group" aria-label="材料类型">
            <label><input type="radio" name="material" checked={material === 'answer-key'} onChange={() => setMaterial('answer-key')} />答案卷 / 评分标准</label>
            <label><input type="radio" name="material" checked={material === 'upload'} onChange={() => setMaterial('upload')} />学生已作答的卷子</label>
          </div>
          <div className="creation-drop" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) addFiles(Array.from(e.dataTransfer.files)) }}>
            <Icon name="upload" size={28} /><div><strong>拖入材料，或选择文件</strong><p>照片、PDF、ZIP、HEIC · 下一步可预览并核对</p></div>
            <label className="file-button">选择文件<input type="file" multiple accept={ACCEPT} onChange={e => { addFiles(Array.from(e.target.files || [])); e.target.value = '' }} /></label>
          </div>
          {!!files.length && <ul className="creation-file-list">{files.map((f, i) => <li key={`${f.name}-${i}`}><span>{f.name}</span><button type="button" aria-label={`移除 ${f.name}`} onClick={() => setFiles(old => old.filter((_, j) => j !== i))}>移除</button></li>)}</ul>}
          <p className="hint">{material === 'answer-key' ? '有答案的材料会进入识别与核对页面，老师确认后才保存为评分依据。空白题卷请先补充参考答案或评分要求。' : '学生卷子会进入上传预览，确认上传后开始批改。没有答案卷时采用 AI 建议答案，请老师复核。'}</p>
        </fieldset>
        <details className="grading-rules-editor">
          <summary>评分规则与步骤分</summary><p className="hint">{gradingRules[subject]}</p>
          <label>本次作业的评分细则（可选）<textarea disabled={busy} rows={4} maxLength={6000} value={rules} onChange={e => setRules(e.target.value)} placeholder="例如：第3题列式2分、计算2分、结论1分；接受等价方法。作文可填写内容、结构和语言的分值。" /></label>
          <p className="hint">老师细则优先；未指定的主观题标准由 AI 建议。创建后可在答案卷页面修改。</p>
        </details>
        {error && <p role="alert" className="err">{error}</p>}
        <div className="creation-submit"><button className="btn-primary" disabled={!room || busy || !title.trim()}>{busy ? '正在创建…' : files.length ? material === 'answer-key' ? '创建并核对答案' : '创建并预览卷子' : '创建作业'}</button><Link to="/">取消</Link><span className="hint">{room?.name}{files.length ? ` · 已选 ${files.length} 个文件` : ''}</span></div>
      </form>
      <aside className="creation-guide" aria-label="创建后的操作">
        <h2>接下来这样完成批改</h2><p>每份作业单独核对答案、跟进进度，随时查看学生原卷。</p>
        <ol><li><strong>核对评分依据</strong><p>上传答案卷，或填写参考答案与步骤分。作文按维度评分。</p></li><li><strong>上传学生卷子</strong><p>支持批量添加。全部上传成功后，自动进入批改进度。</p></li><li><strong>跟进与复核</strong><p>查看实时百分比，处理待认领和需复核题目，再对照原卷确认成绩。</p></li></ol>
        <p className="hint">不确定的字迹、解法和评分由老师最终确认。</p>
      </aside>
    </div>
  </WorkShell>
}
