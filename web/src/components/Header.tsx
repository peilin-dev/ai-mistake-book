import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { clearToken } from '../lib/auth'
import { request } from '../lib/api'

interface Me {
  id: number
  display_name: string
}

/** Shared page header: brand + teacher name + logout. `teacherName` overrides the fetched name. */
export default function Header({ teacherName }: { teacherName?: string }) {
  const navigate = useNavigate()
  const [name, setName] = useState<string>('')

  useEffect(() => {
    if (teacherName !== undefined) return
    let alive = true
    request<Me>('GET', '/api/me')
      .then((m) => alive && setName(m.display_name))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [teacherName])

  const shown = teacherName ?? name
  return (
    <header className="header">
      <span className="brand">红笔君</span>
      <span className="spacer" />
      {shown && <span className="who">{shown}</span>}
      <button
        type="button"
        onClick={() => {
          clearToken()
          navigate('/login', { replace: true })
        }}
      >
        退出登录
      </button>
    </header>
  )
}