import { useRef, useState } from 'react'
import { errorText, request } from '../lib/api'
import { publishMe, type MeInfo } from '../lib/me'
import { credentialError } from '../lib/account'
export default function Credentials({ me }: { me: MeInfo }) {
  const [loginName, setLoginName] = useState(me.login_name ?? ''),
    [password, setPassword] = useState(''),
    [current, setCurrent] = useState(''),
    [confirmation, setConfirmation] = useState(''),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [error, setError] = useState('')
  const lock = useRef(false)
  return (
    <section className="acct-section credentials">
      <h3>登录名和密码</h3>
      <p className="acct-hint">
        {me.login_name
          ? '修改密码时请填写当前密码。'
          : '设置登录名和密码，以后可以不用手机扫码。'}
      </p>
      <label>
        登录名
        <input
          autoComplete="username"
          value={loginName}
          onChange={(e) => setLoginName(e.target.value)}
        />
      </label>
      {me.login_name && (
        <label>
          当前密码
          <input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
      )}
      <label>
        新密码
        <input
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <label>
        确认新密码
        <input
          type="password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
        />
      </label>
      {error && (
        <p className="err" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <button
        disabled={busy}
        onClick={async () => {
          if (lock.current) return
          setMessage('')
          const invalid = credentialError(loginName, password)
          if (invalid) return setError(invalid)
          if (password !== confirmation) return setError('两次输入的密码不一致')
          if (me.login_name && !current) return setError('请填写当前密码')
          lock.current = true
          setBusy(true)
          setError('')
          try {
            const out = await request<MeInfo>('PUT', '/api/me/credentials', {
              login_name: loginName.trim(),
              password,
              current_password: me.login_name ? current : null,
            })
            publishMe(out)
            setPassword('')
            setCurrent('')
            setConfirmation('')
            setMessage('登录名和密码已保存')
          } catch (e) {
            setError(errorText(e))
          } finally {
            lock.current = false
            setBusy(false)
          }
        }}
      >
        保存登录设置
      </button>
    </section>
  )
}
