import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import Header from './Header'
import Brand from './Brand'
export default function WorkShell({
  title,
  description,
  children,
  publicPage = false,
}: {
  title: string
  description?: string
  children: ReactNode
  publicPage?: boolean
}) {
  return (
    <>
      {publicPage ? (
        <header className="header">
          <Link className="brand" to="/login">
            <Brand />
          </Link>
        </header>
      ) : (
        <Header />
      )}
      <main id="main-content" className="page work-page" tabIndex={-1}>
        <Link to="/" className="back">
          ← 返回班级作业
        </Link>
        <div className="page-heading">
          <div>
            <h1>{title}</h1>
            {description && <p>{description}</p>}
          </div>
        </div>
        {children}
      </main>
    </>
  )
}
