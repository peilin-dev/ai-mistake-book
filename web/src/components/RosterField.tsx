import { previewRoster } from '../lib/roster'

const PLACEHOLDER = '每行一个学生，可带学号，例如：\n张三\n李四 02\n王五,03'

/** Paste box for a roster with the live "识别到 N 人" count. */
export default function RosterField({ id, label, value, onChange }: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
}) {
  const { count } = previewRoster(value)
  return (
    <div className="field-block">
      <label htmlFor={id}>{label}</label>
      <textarea
        id={id}
        name={id}
        autoComplete="off"
        rows={8}
        placeholder={PLACEHOLDER}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <p className="field-hint" aria-live="polite">{count > 0 ? `识别到 ${count} 人` : '把名单从微信或表格里粘贴到这里'}</p>
    </div>
  )
}
