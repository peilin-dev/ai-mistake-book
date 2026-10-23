import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { setOnUnauthorized } from './lib/api'
import { getToken } from './lib/auth'
import Login from './pages/Login'
import Placeholder from './pages/Placeholder'

function RequireAuth({ children }: { children: JSX.Element }) {
  const location = useLocation()
  if (!getToken()) {
    const from = location.pathname + location.search
    return <Navigate to="/login" replace state={{ from }} />
  }
  return children
}

// Tasks 6-8 replace the Placeholder elements below with the real pages.
export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  useEffect(() => {
    setOnUnauthorized(() => {
      const from = location.pathname + location.search
      navigate('/login', { replace: true, state: { from } })
    })
  }, [navigate, location])

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RequireAuth><Placeholder title="班级与作业" /></RequireAuth>} />
      <Route path="/a/:assignmentId" element={<RequireAuth><Placeholder title="总览" /></RequireAuth>} />
      <Route
        path="/a/:assignmentId/q/:questionNo"
        element={<RequireAuth><Placeholder title="投影" /></RequireAuth>}
      />
      <Route
        path="/a/:assignmentId/downloads"
        element={<RequireAuth><Placeholder title="下载" /></RequireAuth>}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}