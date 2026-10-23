import { expect, it } from 'vitest'
import { safeReturnPath } from '../src/lib/safePath'
it('keeps internal return destinations including query and hash', () => {
  expect(safeReturnPath('/a/8/work?q=math#pending')).toBe('/a/8/work?q=math#pending')
})
it('rejects external, protocol-relative, backslash and control-character destinations', () => {
  for(const value of [undefined,1,'https://example.com','//example.com','/\\example.com','/\n/evil','javascript:alert(1)']) expect(safeReturnPath(value)).toBe('/')
})
