import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Brand from './Brand'
import Icon from './Icon'
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
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <Link className="brand" to="/" aria-label="红笔君，返回班级"><Brand /></Link>
      <Link className="header-workspace" to="/">老师工作台</Link>
      <span className="spacer" />
      <span className="who"><span className="avatar" aria-hidden="true">{(shown || '老师').slice(0, 1)}</span>{shown || '老师'}</span>
      <button
        type="button"
        onClick={() => {
          clearToken()
          navigate('/login', { replace: true })
        }}
      >
        <Icon name="logout" size={16} /><span>退出登录</span>
      </button>
    </header>
  )
}
