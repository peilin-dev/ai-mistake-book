export interface GroupStudent {
  student_id?: number
  student_name?: string
  submission_id: number
  score?: number
  max_score?: number
}

export interface WrongGroup {
  answer: string
  key: string
  count: number
  students: GroupStudent[]
}

export interface Crop {
  student_name?: string
  submission_id: number
  crop_url: string
}

export interface ScoreBucket {
  label: string
  count: number
}

export interface QuestionDetail {
  question_no: string
  question_text: string | null
  correct_answer: string | null
  is_subjective: boolean
  knowledge_point: string | null
  wrong_count: number
  student_count: number
  answered_count: number
  groups: WrongGroup[]
  score_buckets: ScoreBucket[]
  crops: Crop[]
}

/** Attach each crop url to the group whose student has the same submission_id; strays are dropped. */
export function cropsByGroup(
  groups: { key: string; students: { submission_id: number }[] }[],
  crops: { submission_id: number; crop_url: string }[],
): Map<string, string[]> {
  const owner = new Map<number, string>()
  const out = new Map<string, string[]>()
  for (const g of groups) {
    out.set(g.key, [])
    for (const s of g.students) owner.set(s.submission_id, g.key)
  }
  for (const c of crops) {
    const key = owner.get(c.submission_id)
    if (key !== undefined) out.get(key)!.push(c.crop_url)
  }
  return out
}

export function neighbors(order: string[], current: string): { prev: string | null; next: string | null } {
  const i = order.indexOf(current)
  if (i < 0) return { prev: null, next: null }
  return { prev: i > 0 ? order[i - 1] : null, next: i < order.length - 1 ? order[i + 1] : null }
}
