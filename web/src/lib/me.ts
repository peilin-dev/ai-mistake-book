/** Tiny shared "me" channel: whoever saves the profile publishes it, the Header (and anyone else) follows. */
export interface MeInfo {
  id: number
  display_name: string | null
  last_subject?: string | null
  login_name?: string | null
  quota_total?: number
  quota_used?: number
}

type Listener = (m: MeInfo) => void
const listeners = new Set<Listener>()

export function publishMe(m: MeInfo): void {
  listeners.forEach((fn) => fn(m))
}

export function subscribeMe(fn: Listener): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}
