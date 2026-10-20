import { describe, expect, it, vi } from 'vitest'

const taro = vi.hoisted(() => ({ getImageInfo: vi.fn(), compressImage: vi.fn() }))
vi.mock('@tarojs/taro', () => ({ default: taro }))
import { compressForUpload, targetSize } from '../src/lib/resize'

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


describe('compressForUpload', () => {
  it('resizes a big photo', async () => {
    taro.getImageInfo.mockResolvedValue({ width: 4000, height: 3000 })
    taro.compressImage.mockResolvedValue({ tempFilePath: 'tmp://a.jpg' })
    expect(await compressForUpload('wx://p.jpg')).toBe('tmp://a.jpg')
    expect(taro.compressImage).toHaveBeenCalledWith({
      src: 'wx://p.jpg', quality: 85, compressedWidth: 2000, compressedHeight: 1500,
    })
  })
  it('only re-encodes a photo that already fits', async () => {
    taro.getImageInfo.mockResolvedValue({ width: 800, height: 600 })
    taro.compressImage.mockResolvedValue({ tempFilePath: 'tmp://b.jpg' })
    await compressForUpload('wx://q.jpg')
    expect(taro.compressImage).toHaveBeenLastCalledWith({ src: 'wx://q.jpg', quality: 85 })
  })
})
