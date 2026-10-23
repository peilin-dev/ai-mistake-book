import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { errorText, request } from '../lib/api'
import { setToken } from '../lib/auth'
import { createTicket, qrDataUrl, startPolling, type Ticket } from '../lib/login'
import Brand from '../components/Brand'
import Icon from '../components/Icon'
import RedCircle from '../components/RedCircle'

type View = 'pending' | 'scanned' | 'expired'

export default function Login({ previewOnly = false }: { previewOnly?: boolean }) {
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/'
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [view, setView] = useState<View>('pending')
  const [error, setError] = useState('')
  const stopRef = useRef<() => void>(() => {})
  const genRef = useRef(0)

  const finish = useCallback(
    (token: string) => {
      setToken(token)
      navigate(from, { replace: true })
    },
    [navigate, from],
  )

  const load = useCallback(async () => {
    stopRef.current()
    const gen = ++genRef.current
    setError('')
    setView('pending')
    try {
      const t = await createTicket()
      if (gen !== genRef.current) return
      setTicket(t)
      stopRef.current = startPolling(
        t,
        (s) => setView(s === 'cancelled' ? 'expired' : s),
        finish,
      )
    } catch (e) {
      if (gen !== genRef.current) return
      setTicket(null)
      setError(errorText(e))
    }
  }, [finish])

  useEffect(() => {
    if (previewOnly) return
    void load()
    return () => {
      genRef.current++
      stopRef.current()
    }
  }, [load, previewOnly])

  const devLogin = async () => {
    try {
      const r = await request<{ token: string }>('POST', '/api/auth/dev-login', { teacher_id: null })
      stopRef.current()
      finish(r.token)
    } catch (e) {
      setError(errorText(e))
    }
  }

  return (
    <main id="main-content" className="login-shell">
      <section className="login-story">
        <div className="brand"><Brand size={40} /></div>
        <div className="login-message"><h1>认真批改，<br />从容<RedCircle>讲评</RedCircle>。</h1><p>把整理错题的时间，<br />留给真正需要讲清楚的那道题。</p><div className="login-values"><span><Icon name="check" size={17} />班级学情，一目了然</span><span><Icon name="check" size={17} />错题与练习，随时打印</span></div></div>
        <p className="login-signature">老师的每一笔，都有意义。</p>
      </section>
      <section className="login" aria-labelledby="login-heading">
      <h2 id="login-heading" className="serif">欢迎回到红笔君</h2>
      <p className="hint">用微信扫一扫，在小程序里确认登录</p>
      {error && <p className="err" role="alert">{error}</p>}
      {previewOnly ? <div className="qr-loading preview-login-placeholder"><Icon name="pen" size={38} /><strong>登录码展示区域</strong><span>界面预览，无需扫码</span></div> : !ticket && !error && <div className="qr-loading" role="status">正在准备登录码…</div>}
      {ticket && (
        <>
          <div className={'qr-wrap' + (view === 'expired' ? ' dim' : '')}>
            <img className="qr" width="220" height="220" src={qrDataUrl(ticket.qr_png)} alt="小程序码" />
            {view === 'expired' && (
              <button type="button" className="refresh" onClick={() => void load()}>
                二维码已过期，点击刷新
              </button>
            )}
          </div>
          <p className="pair-label">请核对手机上的数字</p><div className="pair">{ticket.pair_code}</div>
          {view === 'scanned' && <p className="scanned" role="status">已扫码，请在手机上确认</p>}
        </>
      )}
      {!ticket && error && (
        <button type="button" onClick={() => void load()}>
          重试
        </button>
      )}
      {import.meta.env.DEV && !previewOnly && (
        <button type="button" className="dev" onClick={() => void devLogin()}>
          开发者登录
        </button>
      )}
      <p className="login-bottom">手机拍卷 · 电脑讲评 · 两端同步</p>
      </section>
    </main>
  )
}
