import Taro from '@tarojs/taro'
import { API_BASE } from './config'

export const TOKEN_KEY = 'token'

export function getToken(): string {
  return (Taro.getStorageSync(TOKEN_KEY) as string) || ''
}

/** Silent login: wx code -> backend token, stored for later requests. */
export async function login(): Promise<void> {
  const { code } = await Taro.login()
  const res = await Taro.request({
    url: `${API_BASE}/api/auth/wx-login`,
    method: 'POST',
    data: { code },
    header: { 'Content-Type': 'application/json' },
  })
  if (res.statusCode < 200 || res.statusCode >= 300 || !res.data?.token) {
    const detail = typeof res.data?.detail === 'string' ? res.data.detail : 'login failed'
    throw new Error(detail)
  }
  Taro.setStorageSync(TOKEN_KEY, res.data.token)
}