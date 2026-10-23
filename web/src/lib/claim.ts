export function nextIndex(list: number[], current: number): number {
  const i = list.indexOf(current)
  return i < 0 || i + 1 >= list.length ? -1 : i + 1
}
