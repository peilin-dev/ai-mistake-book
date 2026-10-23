import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import WorkShell from '../components/WorkShell'
import { errorText, request } from '../lib/api'
import { setToken } from '../lib/auth'
import { credentialError } from '../lib/account'
import { safeReturnPath } from '../lib/safePath'
export default function Register() {
  const navigate = useNavigate(),
    location = useLocation()
  const [name, setName] = useState(''),
    [password, setPassword] = useState(''),
    [confirmation, setConfirmation] = useState(''),
    [code, setCode] = useState(''),
    [captcha, setCaptcha] = useState<{ captcha_id: string; image: string }>(),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  const lock = useRef(false),
    generation = useRef(0)
  async function refresh() {
    const gen = ++generation.current
    setCaptcha(undefined)
    setCode('')
    try {
      const r = await request<{ captcha_id: string; image: string }>(
        'POST',
        '/api/auth/captcha',
      )
      if (gen === generation.current) setCaptcha(r)
    } catch (e) {
      setError(errorText(e))
    }
  }
  useEffect(() => {
    void refresh()
    return () => {
      generation.current++
    }
  }, [])
  return (
    <WorkShell
      publicPage
      title="注册红笔君"
      description="注册后即可在电脑上管理班级、上传卷子。"
    >
      <form
        className="work-form"
        onSubmit={async (e) => {
          e.preventDefault()
          if (lock.current) return
          const invalid = credentialError(name, password)
          if (invalid) return setError(invalid)
          if (password !== confirmation) return setError('两次输入的密码不一致')
          if (!captcha || !code.trim()) return setError('请填写图形验证码')
          lock.current = true
          setBusy(true)
          setError('')
          try {
            const r = await request<{ token: string }>(
              'POST',
              '/api/auth/register',
              {
                login_name: name.trim(),
                password,
                captcha_id: captcha.captcha_id,
                captcha_code: code.trim(),
              },
            )
            setToken(r.token)
            navigate(
              safeReturnPath((location.state as { from?: string } | null)?.from),
              { replace: true },
            )
          } catch (e) {
            setError(errorText(e))
            await refresh()
          } finally {
            lock.current = false
            setBusy(false)
          }
        }}
      >
        <label>
          登录名
          <input
            autoComplete="username"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={32}
          />
        </label>
        <p className="hint">4–32 位字母、数字或下划线</p>
        <label>
          密码
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            maxLength={64}
          />
        </label>
        <label>
          确认密码
          <input
            type="password"
            autoComplete="new-password"
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            required
          />
        </label>
        <label>
          图形验证码
          <input
            autoComplete="off"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
        </label>
        <button
          type="button"
          className="captcha"
          onClick={() => void refresh()}
          aria-label="更换验证码"
        >
          {captcha ? (
            <img
              src={
                captcha.image.startsWith('data:')
                  ? captcha.image
                  : `data:image/png;base64,${captcha.image}`
              }
              alt="图形验证码，点击更换"
            />
          ) : (
            '加载验证码'
          )}
          <span>换一张</span>
        </button>
        {error && (
          <p role="alert" className="err">
            {error}
          </p>
        )}
        <button className="btn-primary" disabled={busy || !captcha}>
          {busy ? '正在注册…' : '注册'}
        </button>
        <p>
          <Link to="/login" state={location.state}>
            已有账号，去登录
          </Link>
        </p>
      </form>
    </WorkShell>
  )
}
