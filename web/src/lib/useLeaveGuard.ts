import { useEffect, useSyncExternalStore } from 'react'
let state = { active: false, message: '' }
const listeners = new Set<() => void>()
function publish(active: boolean, message: string) {
  state = { active, message }
  listeners.forEach((fn) => fn())
}
export function useLeaveGuard(active: boolean, message: string) {
  useEffect(() => {
    publish(active, message)
    return () => publish(false, '')
  }, [active, message])
}
export function useLeaveState() {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn)
      return () => {
        listeners.delete(fn)
      }
    },
    () => state,
  )
}
