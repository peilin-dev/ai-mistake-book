const CN = ['一', '二', '三', '四', '五', '六', '七', '八', '九']

/** Grade picker options, 1–9 only. */
export const GRADE_LABELS: string[] = CN.map((c) => `${c}年级`)

export const DEFAULT_GRADE = 5

export function defaultClassName(grade: number): string {
  return `${CN[grade - 1] ?? CN[DEFAULT_GRADE - 1]}年级1班`
}
