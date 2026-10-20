import { describe, expect, it, vi } from 'vitest'

vi.mock('@tarojs/taro', () => ({ default: {} }))
import { targetSize } from '../src/lib/resize'

describe('targetSize', () => {
  it('shrinks the long edge to 2000', () => {
    expect(targetSize(4000, 3000)).toEqual({ width: 2000, height: 1500 })
    expect(targetSize(3000, 4000)).toEqual({ width: 1500, height: 2000 })
  })
  it('never enlarges', () => {
    expect(targetSize(800, 600)).toEqual({ width: 800, height: 600 })
    expect(targetSize(2000, 2000)).toEqual({ width: 2000, height: 2000 })
  })
  it('rounds to integers, min 1', () => {
    expect(targetSize(3001, 1999)).toEqual({ width: 2000, height: 1332 })
    expect(targetSize(10000, 1)).toEqual({ width: 2000, height: 1 })
  })
  it('custom max', () => {
    expect(targetSize(1000, 500, 100)).toEqual({ width: 100, height: 50 })
  })
})

