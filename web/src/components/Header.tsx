import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Brand from './Brand'
import Icon from './Icon'
import { clearToken } from '../lib/auth'
import { request } from '../lib/api'
import { publishMe, subscribeMe, type MeInfo } from '../lib/me'
import AccountDialog from './AccountDialog'

/** Shared page header: brand + teacher name (opens account settings) + logout. `teacherName` overrides the fetched name. */
export default function Header({ teacherName }: { teacherName?: string }) {
  const navigate = useNavigate()
  const [me, setMe] = useState<MeInfo | null>(null)
  const [open, setOpen] = useState(false)

  const load = () =>
    request<MeInfo>('GET', '/api/me').then((m) => publishMe(m)).catch(() => {})

  useEffect(() => subscribeMe((m) => setMe((prev) => ({ ...prev, ...m }))), [])
  useEffect(() => {
    if (teacherName === undefined) void load()
  }, [teacherName])

  const name = me?.display_name?.trim() ?? ''
  const shown = teacherName ?? name
  const who = (
    <>
      <span className="avatar" aria-hidden="true">{(shown || '老师').slice(0, 1)}</span>
      {teacherName !== undefined ? shown || '老师' : name || '设置署名'}
    </>
  )
  return (
    <header className="header">
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <Link className="brand" to="/" aria-label="红笔君，返回班级"><Brand /></Link>
      <Link className="header-workspace" to="/">老师工作台</Link>
      <span className="spacer" />
      {teacherName !== undefined || !me ? (
        <span className="who">{who}</span>
      ) : (
        <button
          type="button"
          className="who who-btn"
          aria-haspopup="dialog"
          onClick={() => { setOpen(true); void load() }}
        >
          {who}
        </button>
      )}
      {open && me && <AccountDialog me={me} onClose={() => setOpen(false)} />}
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
