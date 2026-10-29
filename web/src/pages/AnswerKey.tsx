import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import Confirm from '../components/Confirm'
import GradingRulesEditor, { type AssignmentContext } from '../components/GradingRulesEditor'
import { subjectLabel, type ClassOut } from '../lib/overview'
import { errorText, request } from '../lib/api'
import {
  ACCEPT,
  expandFiles,
  imageBody,
  MAX_BATCH,
  toJpeg,
  type SourcePage,
} from '../lib/intake'
import {
  blankRow,
  toRows,
  toPutBody,
  validateRows,
  type KeyRow,
  type AnswerKeyItem,
} from '../lib/answerKey'
import { mergeKeys } from '../lib/answerKeyMerge'
import { useLeaveGuard } from '../lib/useLeaveGuard'
import { takeAssignmentMaterials } from '../lib/assignmentMaterials'
type Extraction = {
  page: SourcePage
  items?: AnswerKeyItem[]
  error?: string
  skipped?: boolean
}
export default function AnswerKey() {
  const { assignmentId } = useParams()
  return <AnswerKeyEditor key={assignmentId} />
}
function AnswerKeyEditor() {
  const { assignmentId } = useParams(),
    path = `/api/assignments/${assignmentId}/answer-key`
  const [assignment, setAssignment] = useState<AssignmentContext>(), [classes, setClasses] = useState<ClassOut[]>([])
  const [deleting, setDeleting] = useState(false), [hasKey, setHasKey] = useState(false)
  useEffect(() => {
    let live = true
    request<ClassOut[]>('GET', '/api/classes').then(list => { if (live && Array.isArray(list)) setClasses(list) }).catch(() => {})
    return () => { live = false }
  }, [])
  const [rows, setRows] = useState<KeyRow[]>([]),
    [extractions, setExtractions] = useState<Extraction[]>([]),
    [overridden, setOverridden] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false),
    [confirmed, setConfirmed] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [pending, setPending] = useState<File[]>()
  const lock = useRef(false),
    input = useRef<HTMLInputElement>(null),
    controller = useRef<AbortController>(),
    mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      controller.current?.abort()
    }
  }, [])
  const [dirty, setDirty] = useState(false)
  useLeaveGuard(
    busy || dirty,
    busy ? '答案卷还在处理，确定离开吗？' : '核对内容还没有保存，确定离开吗？',
  )
  useEffect(() => {
    let live = true
    request<{ items: AnswerKeyItem[]; answer_key_status: string }>('GET', path)
      .then((r) => {
        if (live) {
          setRows(toRows(r.items))
          setConfirmed(r.answer_key_status === 'confirmed')
          setHasKey(r.answer_key_status !== 'none')
          setLoaded(true)
        }
      })
      .catch((e) => live && setError(errorText(e)))
    return () => {
      live = false
    }
  }, [path])
  function merge(list: Extraction[]) {
    const result = mergeKeys(
      list.flatMap((p, pageIndex) =>
        p.items && !p.skipped ? [{ pageIndex, items: p.items }] : [],
      ),
    )
    setRows(toRows(result.items))
    setOverridden(result.overridden)
    setDirty(true)
  }
  async function extract(page: SourcePage): Promise<Extraction> {
    try {
      const r = await request<{ items: AnswerKeyItem[] }>(
        'POST',
        path,
        imageBody(await toJpeg(await page.load())),
        controller.current?.signal,
      )
      if (mounted.current) setHasKey(true)
      return { page, items: r.items }
    } catch (e) {
      return {
        page,
        error:
          e instanceof Error && /图片|HEIC/.test(e.message)
            ? e.message
            : errorText(e),
      }
    }
  }
  async function start(files: File[]) {
    if (lock.current) return
    lock.current = true
    controller.current = new AbortController()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await expandFiles(files)
      if (!mounted.current) return
      if (result.bad.length)
        throw new Error(
          result.bad.map((b) => `${b.fileName}：${b.reason}`).join('；'),
        )
      if (!result.pages.length) throw new Error('没有可识别的图片或 PDF 页')
      if (result.pages.length > MAX_BATCH)
        throw new Error('一次最多处理 200 页，请分批上传')
      const list: Extraction[] = result.pages.map((page) => ({ page }))
      setExtractions([...list])
      setConfirmed(false)
      for (let i = 0; i < list.length; i++) {
        if (controller.current.signal.aborted) return
        list[i] = await extract(list[i].page)
        if (!mounted.current) return
        setExtractions([...list])
      }
      merge(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : errorText(e))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }
  async function retry(i: number) {
    if (lock.current) return
    lock.current = true
    controller.current = new AbortController()
    setBusy(true)
    const list = [...extractions]
    list[i] = await extract(list[i].page)
    if (!mounted.current) return
    setExtractions(list)
    merge(list)
    lock.current = false
    setBusy(false)
  }
  const update = (key: string, values: Partial<KeyRow>) => {
    setDirty(true)
    setRows((old) => old.map((r) => (r.key === key ? { ...r, ...values } : r)))
    setNotice('')
  }
  const unresolved = extractions.some((p) => !p.items && !p.skipped)
  useEffect(() => {
    if (!loaded) return
    const timer = setTimeout(() => {
      const files = takeAssignmentMaterials(Number(assignmentId))
      if (files.length) void start(files)
    }, 0)
    return () => clearTimeout(timer)
  }, [loaded, assignmentId])
  return (
    <WorkShell
      title="答案卷核对"
      description="识别出的答案需要老师确认。请尽量在上传学生试卷前保存答案卷。"
    >
      {error && (
        <p role="alert" className="err">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <section className="answer-key-context" aria-label="答案卷所属作业">
        <div><h2>{assignment?.title || `当前作业 #${assignmentId}`}</h2><p>{classes.find(c => c.id === assignment?.class_id)?.name || (assignment?.class_id ? `班级 #${assignment.class_id}` : '当前班级')}{assignment?.subject ? ` · ${subjectLabel(assignment.subject)}` : ''} · 作业 #{assignmentId}</p></div>
        <p className="hint">本页答案只用于这份作业。上传前请核对作业名称、题号与试卷一致。</p>
      </section>
      <GradingRulesEditor assignmentId={assignmentId!} onAssignment={setAssignment} />
      <div className="work-actions">
        <label className="file-button btn-primary">
          {busy ? '正在处理…' : confirmed ? '重新上传答案卷' : '选择答案卷'}
          <input
            ref={input}
            disabled={busy || !loaded}
            type="file"
            multiple
            accept={ACCEPT}
            onChange={(e) => {
              const files = Array.from(e.target.files ?? [])
              e.target.value = ''
              if (!files.length) return
              if (confirmed || dirty) setPending(files)
              else void start(files)
            }}
          />
        </label>
        <span>
          {confirmed
            ? '已确认保存'
            : '支持照片、多页 PDF 和 ZIP，也可直接手动填写'}
        </span>
        {(hasKey || rows.length > 0) && <button className="answer-key-delete" disabled={busy || !loaded} onClick={() => setDeleting(true)}>删除整份答案卷</button>}
      </div>
      {!!extractions.length && (
        <section className="notice" aria-label="答案提取进度">
          <p>
            已处理{' '}
            {extractions.filter((p) => p.items || p.error || p.skipped).length}{' '}
            / {extractions.length} 页
          </p>
          {extractions.map((p, i) => (
            <p key={p.page.id}>
              第 {i + 1} 页：{p.page.fileName} ·{' '}
              {p.skipped
                ? '已跳过'
                : p.error ||
                  (p.items ? `提取 ${p.items.length} 题` : '等待提取…')}
              {p.error && !p.skipped && (
                <>
                  <button disabled={busy} onClick={() => void retry(i)}>
                    重试这一页
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => {
                      const list = extractions.map((r, j) =>
                        j === i ? { ...r, skipped: true } : r,
                      )
                      setExtractions(list)
                      merge(list)
                    }}
                  >
                    跳过
                  </button>
                </>
              )}
            </p>
          ))}
        </section>
      )}
      {!!overridden.length && (
        <p className="notice">
          题号 {overridden.join('、')} 在多页里都有，已取后页答案，请核对。
        </p>
      )}
      <fieldset disabled={busy || !loaded || unresolved} className="key-editor">
        <legend className="serif">核对题号、答案和分值</legend>
        <div className="table-scroll">
          <table className="work-table">
            <thead>
              <tr>
                <th>题号</th>
                <th>答案</th>
                <th>分值（可空）</th>
                <th>主观题</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.key}>
                  <td>
                    <input
                      aria-label={`第 ${i + 1} 行题号`}
                      value={r.question_no}
                      onChange={(e) =>
                        update(r.key, { question_no: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    <textarea
                      aria-label={`第 ${i + 1} 行答案`}
                      value={r.answer}
                      onChange={(e) =>
                        update(r.key, { answer: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`第 ${i + 1} 行分值`}
                      type="number"
                      min="0"
                      step="any"
                      value={r.max_score}
                      onChange={(e) =>
                        update(r.key, { max_score: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`第 ${i + 1} 行主观题`}
                      type="checkbox"
                      checked={r.is_subjective}
                      onChange={(e) =>
                        update(r.key, { is_subjective: e.target.checked })
                      }
                    />
                  </td>
                  <td>
                    <button
                      onClick={() => {
                        setRows((old) => old.filter((x) => x.key !== r.key))
                        setDirty(true)
                      }}
                    >
                      删行
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button
          onClick={() => {
            setRows((old) => [...old, blankRow()])
            setDirty(true)
          }}
        >
          加一行
        </button>
      </fieldset>
      <div className="work-actions">
        <button
          className="btn-primary"
          disabled={busy || !loaded || unresolved || !rows.length}
          onClick={async () => {
            if (lock.current) return
            const invalid = validateRows(rows)
            if (invalid) {
              setError(invalid)
              return
            }
            lock.current = true
            setBusy(true)
            setError('')
            try {
              const out = await request<{ regrade_suggested: boolean }>(
                'PUT',
                path,
                toPutBody(rows),
              )
              setConfirmed(true)
              setHasKey(true)
              setDirty(false)
              setNotice(
                out.regrade_suggested
                  ? '答案已保存。已有批改结果不会自动重算，请复核已批改的题目。'
                  : '答案卷已确认保存，可以上传学生试卷了。',
              )
            } catch (e) {
              setError(errorText(e))
            } finally {
              lock.current = false
              setBusy(false)
            }
          }}
        >
          确认保存
        </button>
      </div>
      {pending && (
        <Confirm
          title="替换现有答案卷？"
          message="重新提取会替换现有答案内容。请在本页核对并确认保存后再离开。"
          confirmText="继续上传"
          onCancel={() => setPending(undefined)}
          onConfirm={() => {
            const files = pending
            setPending(undefined)
            void start(files)
          }}
        />
      )}
      {deleting && <Confirm title="删除本作业的整份答案卷？" message={`将清除“${assignment?.title || `作业 #${assignmentId}`}”已保存的参考答案和本页编辑内容。后续批改将使用 AI 建议答案，已有成绩不会自动重算。`} confirmText="删除答案卷" danger onCancel={() => setDeleting(false)} onConfirm={async () => {
        if (lock.current) return
        lock.current = true; setBusy(true); setError(''); setDeleting(false)
        try {
          const out = await request<{ regrade_suggested: boolean }>('DELETE', path)
          setRows([]); setExtractions([]); setOverridden([]); setConfirmed(false); setHasKey(false); setDirty(false); setPending(undefined)
          setNotice(out.regrade_suggested ? '答案卷已删除。后续批改使用 AI 建议答案；已有成绩保留，请按需复核。' : '答案卷已删除，可以重新上传或填写参考答案。')
        } catch (e) { setError(errorText(e)) }
        finally { lock.current = false; setBusy(false) }
      }} />}
    </WorkShell>
  )
}
