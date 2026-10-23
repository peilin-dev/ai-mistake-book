import { ApiError, errorText, request } from './api'
import { imageBody, toJpeg, type SourcePage } from './intake'
export type UploadState =
  | 'waiting'
  | 'uploading'
  | 'done'
  | 'duplicate'
  | 'failed'
  | 'skipped_quota'
export interface UploadResult {
  uploaded: number
  duplicates: number
  failed: number
  quotaStopped: boolean
  skipped: number
}
export async function uploadAll(
  assignmentId: number,
  pages: SourcePage[],
  onChange: (id: string, state: UploadState, err?: string) => void,
  concurrency = 3,
  signal?: AbortSignal,
): Promise<UploadResult> {
  const result: UploadResult = {
    uploaded: 0,
    duplicates: 0,
    failed: 0,
    quotaStopped: false,
    skipped: 0,
  }
  let index = 0
  await Promise.all(
    Array.from(
      { length: Math.min(Math.max(1, concurrency), pages.length) },
      async () => {
        while (
          index < pages.length &&
          !result.quotaStopped &&
          !signal?.aborted
        ) {
          const page = pages[index++]
          onChange(page.id, 'uploading')
          try {
            const blob = await toJpeg(await page.load())
            if (signal?.aborted) return
            if (result.quotaStopped) {
              result.skipped++
              onChange(page.id, 'skipped_quota')
              continue
            }
            const body = imageBody(blob)
            const out = signal
              ? await request<{ duplicate: boolean }>(
                  'POST',
                  `/api/assignments/${assignmentId}/pages?source=web`,
                  body,
                  signal,
                )
              : await request<{ duplicate: boolean }>(
                  'POST',
                  `/api/assignments/${assignmentId}/pages?source=web`,
                  body,
                )
            if (out.duplicate) result.duplicates++
            else result.uploaded++
            onChange(page.id, out.duplicate ? 'duplicate' : 'done')
          } catch (e) {
            if (signal?.aborted) return
            if (e instanceof ApiError && e.status === 429) {
              result.quotaStopped = true
              result.skipped++
              onChange(page.id, 'skipped_quota')
            } else {
              result.failed++
              onChange(
                page.id,
                'failed',
                e instanceof Error && /图片|HEIC/.test(e.message)
                  ? e.message
                  : errorText(e),
              )
            }
          }
        }
      },
    ),
  )
  if (result.quotaStopped)
    for (const page of pages.slice(index)) {
      result.skipped++
      onChange(page.id, 'skipped_quota')
    }
  return result
}
export function summaryText(r: UploadResult) {
  return `上传 ${r.uploaded} 页，跳过重复 ${r.duplicates} 页，失败 ${r.failed} 页${r.quotaStopped ? `。本月额度已用完，剩下 ${r.skipped} 页没有上传` : ''}`
}
