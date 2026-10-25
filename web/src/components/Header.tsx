import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate, useParams } from 'react-router-dom'
import Brand from './Brand'
import Icon from './Icon'
import { clearToken } from '../lib/auth'
import { request } from '../lib/api'
import { publishMe, subscribeMe, type MeInfo } from '../lib/me'
import { workNav, workPath } from '../lib/workNav'
import AccountDialog from './AccountDialog'

export default function Header({ teacherName }: { teacherName?: string }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { assignmentId } = useParams()
  const [me, setMe] = useState<MeInfo | null>(null)
  const [open, setOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const mobileToggle = useRef<HTMLButtonElement>(null)
  const sidebar = useRef<HTMLElement>(null)
  const params = new URLSearchParams(location.search)
  const [search, setSearch] = useState(params.get('q') || '')
  const classView = location.pathname === '/' && params.get('view') === 'classes'
  const currentWork = workNav.find(item => location.pathname === workPath(assignmentId || '', item.path))
  const title = assignmentId ? currentWork?.label || (location.pathname.includes('/students/') ? '学生作答' : '课堂讲评')
    : location.pathname === '/classes/new' ? '新建班级'
    : location.pathname.endsWith('/assignments/new') ? '新建作业'
    : location.pathname.startsWith('/classes/') ? '班级管理'
    : classView ? '我的班级' : '班级作业'

  const load = () => request<MeInfo>('GET', '/api/me').then(publishMe).catch(() => {})
  useEffect(() => subscribeMe(m => setMe(prev => ({ ...prev, ...m }))), [])
  useEffect(() => { if (teacherName === undefined) void load() }, [teacherName])
  useEffect(() => {
    setSearch(new URLSearchParams(location.search).get('q') || '')
    setMobileOpen(false)
  }, [location.pathname, location.search])
  useEffect(() => {
    if (!mobileOpen) return
    sidebar.current?.querySelector<HTMLElement>('a,button')?.focus()
    const before = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileOpen(false)
        mobileToggle.current?.focus()
      } else if (event.key === 'Tab') {
        const items = sidebar.current?.querySelectorAll<HTMLElement>('a,button:not([disabled])')
        if (!items?.length) return
        const first = items[0], last = items[items.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = before; window.removeEventListener('keydown', onKey) }
  }, [mobileOpen])

  const shown = teacherName ?? me?.display_name?.trim() ?? ''
  const accountLabel = teacherName !== undefined ? shown || '老师' : shown || '设置署名'
  const account = <><span className="avatar" aria-hidden="true">{(shown || '老师').slice(0, 1)}</span><span className="account-copy"><strong>{accountLabel}</strong><small>账号与批改额度</small></span><Icon name="chevron" size={16} /></>
  const logout = () => {
    if (!window.dispatchEvent(new Event('teacher-logout', { cancelable: true }))) return
    clearToken()
    navigate('/login', { replace: true })
  }

  return <>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <aside id="workspace-sidebar" ref={sidebar} className={`app-sidebar${collapsed ? ' is-collapsed' : ''}${mobileOpen ? ' is-open' : ''}`} aria-label="工作台侧栏">
      <div className="sidebar-brand"><Link className="brand" to="/" aria-label="红笔君，返回班级"><Brand /></Link><button className="mobile-nav-close" type="button" aria-label="关闭导航" onClick={() => { setMobileOpen(false); mobileToggle.current?.focus() }}><Icon name="close" /></button></div>
      <nav className="primary-nav" aria-label="主导航">
        <Link to="/" className={`sidebar-link${location.pathname === '/' && !classView ? ' active' : ''}`} aria-label="班级作业" aria-current={location.pathname === '/' && !classView ? 'page' : undefined} title="班级作业"><Icon name="home" /><span>班级作业</span></Link>
        <Link to="/?view=classes" className={`sidebar-link${classView || location.pathname.startsWith('/classes/') ? ' active' : ''}`} aria-label="我的班级" aria-current={classView ? 'page' : undefined} title="我的班级"><Icon name="users" /><span>我的班级</span></Link>
      </nav>
      {assignmentId && <div className="sidebar-assignment"><div className="sidebar-group-label"><Icon name="book" size={17} /><span>当前作业</span></div><nav className="assignment-nav" aria-label="作业功能">{workNav.map(item => <NavLink key={item.path} end to={workPath(assignmentId, item.path)} className="sidebar-link" aria-label={item.label} title={item.label}><Icon name={item.icon} size={18} /><span>{item.label}</span></NavLink>)}</nav></div>}
      <div className="sidebar-bottom">
        {me?.quota_total !== undefined && me.quota_used !== undefined && <div className="sidebar-quota"><div><Icon name="file" size={16} /><span>本月批改</span><strong>{me.quota_used} / {me.quota_total} 页</strong></div><progress aria-label="本月批改额度" value={me.quota_used} max={Math.max(1, me.quota_total)} /></div>}
        {teacherName !== undefined || !me ? <div className="sidebar-account">{account}</div> : <button type="button" className="sidebar-account" aria-label={`${accountLabel}，账号与批改额度`} aria-haspopup="dialog" onClick={() => { if (mobileOpen) { setMobileOpen(false); mobileToggle.current?.focus() } setOpen(true); void load() }}>{account}</button>}
        <button type="button" className="sidebar-link logout-link" aria-label="退出登录" onClick={logout} title="退出登录"><Icon name="logout" size={18} /><span>退出登录</span></button>
      </div>
    </aside>
    {mobileOpen && <button className="nav-scrim" type="button" aria-label="收起导航" tabIndex={-1} onClick={() => { setMobileOpen(false); mobileToggle.current?.focus() }} />}
    <header className="header workspace-header">
      <button type="button" className="desktop-nav-toggle icon-button" aria-label={collapsed ? '展开侧边栏' : '折叠侧边栏'} aria-expanded={!collapsed} aria-controls="workspace-sidebar" onClick={() => setCollapsed(!collapsed)}><Icon name="panel" size={20} /></button>
      <button ref={mobileToggle} type="button" className="mobile-nav-toggle icon-button" aria-label="打开导航" aria-expanded={mobileOpen} aria-controls="workspace-sidebar" onClick={() => setMobileOpen(true)}><Icon name="panel" size={20} /></button>
      <span className="topbar-divider" /><span className="topbar-title">{title}</span>
      <form className="topbar-search" role="search" onSubmit={event => {
        event.preventDefault()
        const next = location.pathname === '/' ? new URLSearchParams(location.search) : new URLSearchParams()
        next.delete('view')
        search.trim() ? next.set('q', search.trim()) : next.delete('q')
        navigate(`/${next.toString() ? '?' + next : ''}`)
      }}><Icon name="search" size={19} /><input type="search" aria-label="搜索作业" placeholder="搜索作业…" value={search} onChange={event => setSearch(event.target.value)} /><button type="submit" className="search-submit" aria-label="开始搜索"><Icon name="arrow" size={17} /></button></form>
    </header>
    {open && me && <AccountDialog me={me} onClose={() => setOpen(false)} />}
  </>
}
