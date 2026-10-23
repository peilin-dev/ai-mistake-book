export function credentialError(name: string, password: string): string {
  if (!/^[a-zA-Z0-9_]{4,32}$/.test(name.trim()))
    return '登录名需为 4–32 位字母、数字或下划线'
  if (password.length < 8 || password.length > 64) return '密码需为 8–64 位'
  return ''
}
