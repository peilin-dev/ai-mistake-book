import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { errorText, request } from '../lib/api'
import { setToken } from '../lib/auth'
import { createTicket, qrDataUrl, startPolling, type Ticket } from '../lib/login'

type View = 'pending' | 'scanned' | 'expired'

export default function Login() {
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
    void load()
    return () => {
      genRef.current++
      stopRef.current()
    }
  }, [load])

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
    <main className="login">
      <h1>红笔君</h1>
      <p className="hint">用微信扫一扫，在小程序里确认登录</p>
      {error && <p className="err">{error}</p>}
      {ticket && (
        <>
          <div className={'qr-wrap' + (view === 'expired' ? ' dim' : '')}>
            <img className="qr" src={qrDataUrl(ticket.qr_png)} alt="小程序码" />
            {view === 'expired' && (
              <button type="button" className="refresh" onClick={() => void load()}>
                二维码已过期，点击刷新
              </button>
            )}
          </div>
          <div className="pair">{ticket.pair_code}</div>
          {view === 'scanned' && <p className="scanned">已扫码，请在手机上确认</p>}
        </>
      )}
      {!ticket && error && (
        <button type="button" onClick={() => void load()}>
          重试
        </button>
      )}
      {import.meta.env.DEV && (
        <button type="button" className="dev" onClick={() => void devLogin()}>
          开发者登录
        </button>
      )}
    </main>
  )
}