import type { ReactNode } from 'react'

/**
 * A quick red-pen loop around its child, as a teacher circles an answer.
 * One stroke: starts top right, runs anticlockwise and overshoots past the start without closing.
 * Purely decorative — the child carries the meaning.
 */
const STROKE = 'M93 8C70 1 28 3 12 15C-1 25 4 46 31 53C58 60 103 55 113 39C121 25 107 10 80 7C70 6 62 7 55 10'

export default function RedCircle({ children }: { children: ReactNode }) {
  return (
    <span className="red-circle">
      {children}
      <svg className="red-circle-mark" viewBox="0 0 120 60" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <path d={STROKE} pathLength={1} vectorEffect="non-scaling-stroke" />
      </svg>
    </span>
  )
}
