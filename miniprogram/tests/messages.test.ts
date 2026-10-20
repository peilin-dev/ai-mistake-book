import { describe, expect, it, vi } from 'vitest'

vi.mock('@tarojs/taro', () => ({ default: {} }))

import { ApiError } from '../src/lib/api'
import { errorText, failReasonAction, failReasonText } from '../src/lib/messages'

describe('failReasonText / failReasonAction', () => {
  it('maps known reasons', () => {
    expect(failReasonText('unreadable')).toBe('看不清，请重拍这张')
    expect(failReasonText('model_output_invalid')).toBe('这张没批出来，请重拍')
    expect(failReasonText('model_unavailable')).toBe('批改服务暂时出错，点重试')
    expect(failReasonText('internal_error')).toBe('批改服务暂时出错，点重试')
  })
  it('falls back for unknown or null', () => {
    expect(failReasonText('weird')).toBe('这张没批出来，请重拍')
    expect(failReasonText(null)).toBe('这张没批出来，请重拍')
  })
  it('chooses retry vs retake', () => {
    expect(failReasonAction('model_unavailable')).toBe('retry')
    expect(failReasonAction('internal_error')).toBe('retry')
    expect(failReasonAction('unreadable')).toBe('retake')
    expect(failReasonAction('model_output_invalid')).toBe('retake')
    expect(failReasonAction('weird')).toBe('retake')
    expect(failReasonAction(null)).toBeNull()
  })
})

describe('errorText', () => {
  it('uses backend detail for 409/429/503', () => {
    expect(errorText(new ApiError(429, '本月批改额度已用完'))).toBe('本月批改额度已用完')
    expect(errorText(new ApiError(503, '已收到，稍后会自动开始批改'))).toBe('已收到，稍后会自动开始批改')
    expect(errorText(new ApiError(409, '已有成绩的学生不能删除，可以改名'))).toBe(
      '已有成绩的学生不能删除，可以改名',
    )
  })
  it('network failures', () => {
    expect(errorText(new ApiError(0, ''))).toBe('网络不太好，请稍后再试')
    expect(errorText(new Error('request:fail timeout'))).toBe('网络不太好，请稍后再试')
    expect(errorText({ errMsg: 'request:fail url not in domain list' })).toBe('网络不太好，请稍后再试')
  })
  it('everything else, never a status code', () => {
    expect(errorText(new ApiError(500, 'boom'))).toBe('出了点问题，请稍后再试')
    expect(errorText(new ApiError(404, ''))).toBe('出了点问题，请稍后再试')
    expect(errorText(new Error('x'))).toBe('出了点问题，请稍后再试')
    expect(errorText(undefined)).toBe('出了点问题，请稍后再试')
  })
})
