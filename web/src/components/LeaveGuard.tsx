import { useEffect, useRef } from 'react'
import { useBlocker } from 'react-router-dom'
import { useLeaveState } from '../lib/useLeaveGuard'
export default function LeaveGuard() {
  const { active, message } = useLeaveState()
  const logoutAllowed = useRef(false)
  const blocker = useBlocker(() => active && !logoutAllowed.current)
  useEffect(() => {
    if (blocker.state === 'blocked') {
      if (window.confirm(message)) blocker.proceed()
      else blocker.reset()
    }
  }, [blocker, message])
  useEffect(() => {
    if (!active) {
      logoutAllowed.current = false
      return
    }
    const unload = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = message
    }
    const logout = (e: Event) => {
      if (!window.confirm(message)) e.preventDefault()
      else logoutAllowed.current = true
    }
    window.addEventListener('beforeunload', unload)
    window.addEventListener('teacher-logout', logout)
    return () => {
      window.removeEventListener('beforeunload', unload)
      window.removeEventListener('teacher-logout', logout)
    }
  }, [active, message])
  return null
}
