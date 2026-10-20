// Mirrors backend/app/classes/roster.py parse_roster; keep the two in sync.
export interface RosterPreviewEntry {
  name: string
  studentNo: string | null
}

const STUDENT_NO = /^[A-Za-z]?\d+$/
const COMMA_OR_TAB = /[,，\t]/

function parseLine(line: string): RosterPreviewEntry | null {
  const raw = COMMA_OR_TAB.test(line) ? line.split(/[,，\t]/).map((p) => p.trim()) : line.split(/\s+/)
  const parts = raw.filter((p) => p)
  if (parts.length === 0) return null
  const numberIdx = parts.flatMap((p, i) => (STUDENT_NO.test(p) ? [i] : []))
  if (numberIdx.length !== 1) return { name: parts.join(' '), studentNo: null }
  const no = parts[numberIdx[0]]
  const name = parts.filter((_, i) => i !== numberIdx[0]).join(' ')
  return name ? { name, studentNo: no } : { name: no, studentNo: null }
}

export function previewRoster(text: string): { count: number; entries: RosterPreviewEntry[] } {
  const entries: RosterPreviewEntry[] = []
  const seen = new Set<string>()
  for (const line of text.split(/\r\n|\r|\n/)) {
    const entry = parseLine(line.trim())
    if (!entry) continue
    const key = JSON.stringify([entry.name, entry.studentNo])
    if (seen.has(key)) continue
    seen.add(key)
    entries.push(entry)
  }
  return { count: entries.length, entries }
}
