import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { setOnUnauthorized } from './lib/api'
import { getToken } from './lib/auth'
import Home from './pages/Home'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Downloads from './pages/Downloads'
import Question from './pages/Question'
import ClassNew from './pages/ClassNew'
import ClassDetail from './pages/ClassDetail'

function RequireAuth({ children }: { children: JSX.Element }) {
  const location = useLocation()
  if (!getToken()) {
    const from = location.pathname + location.search
    return <Navigate to="/login" replace state={{ from }} />
  }
  return children
}

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
      <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
      <Route path="/classes/new" element={<RequireAuth><ClassNew /></RequireAuth>} />
      <Route path="/classes/:classId" element={<RequireAuth><ClassDetail /></RequireAuth>} />
      <Route path="/a/:assignmentId" element={<RequireAuth><Overview /></RequireAuth>} />
      <Route
        path="/a/:assignmentId/q/:questionNo"
        element={<RequireAuth><Question /></RequireAuth>}
      />
      <Route
        path="/a/:assignmentId/downloads"
        element={<RequireAuth><Downloads /></RequireAuth>}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}