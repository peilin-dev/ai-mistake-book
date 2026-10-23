export type { ClassOut } from './overview'

export interface StudentOut {
  id: number
  name: string
  student_no: string | null
}

export interface ImportOut {
  created: number
  students: StudentOut[]
}

/** `recognized` = people found in the pasted text (already de-duplicated), `created` = actually added. */
export function importNotice(recognized: number, created: number): string {
  return `新增 ${created} 人，跳过重复 ${Math.max(recognized - created, 0)} 人`
}
