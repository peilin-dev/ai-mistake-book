// Keep selected local files across the creation -> upload route only.
// Files never enter URLs, browser history, localStorage or a real API here.
const pending = new Map<number, File[]>()
export function stageAssignmentMaterials(assignmentId: number, files: File[]) {
  pending.set(assignmentId, files)
}
export function takeAssignmentMaterials(assignmentId: number): File[] {
  const files = pending.get(assignmentId) || []
  pending.delete(assignmentId)
  return files
}
