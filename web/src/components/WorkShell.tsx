import type { ReactNode } from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
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
  const { assignmentId } = useParams()
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
        {assignmentId && (
          <nav className="work-nav" aria-label="作业功能">
            {[
              ['work', '批改进度'],
              ['answer-key', '答案卷'],
              ['upload', '上传卷子'],
              ['claim', '待认领'],
              ['review', '复核'],
              ['grades', '成绩'],
              ['practice', '练习卷'],
              ['', '学情'],
              ['downloads', '下载打印'],
            ].map(([path, label]) => (
              <NavLink
                end
                key={path}
                to={`/a/${assignmentId}${path ? '/' + path : ''}`}
              >
                {label}
              </NavLink>
            ))}
          </nav>
        )}
        {children}
      </main>
    </>
  )
}
