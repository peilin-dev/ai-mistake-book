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
import AssignmentNew from './pages/AssignmentNew'
import AssignmentWork from './pages/AssignmentWork'
import Upload from './pages/Upload'
import Claim from './pages/Claim'
import AnswerKey from './pages/AnswerKey'
import Register from './pages/Register'
import Review from './pages/Review'
import Grades from './pages/Grades'
import Student from './pages/Student'
import Practice from './pages/Practice'

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
      <Route path="/register" element={<Register />} />
      <Route path="/classes/:classId/assignments/new" element={<RequireAuth><AssignmentNew /></RequireAuth>} />
      <Route path="/a/:assignmentId/work" element={<RequireAuth><AssignmentWork /></RequireAuth>} />
      <Route path="/a/:assignmentId/upload" element={<RequireAuth><Upload /></RequireAuth>} />
      <Route path="/a/:assignmentId/claim" element={<RequireAuth><Claim /></RequireAuth>} />
      <Route path="/a/:assignmentId/answer-key" element={<RequireAuth><AnswerKey /></RequireAuth>} />
      <Route path="/a/:assignmentId/review" element={<RequireAuth><Review /></RequireAuth>} />
      <Route path="/a/:assignmentId/grades" element={<RequireAuth><Grades /></RequireAuth>} />
      <Route path="/a/:assignmentId/students/:submissionId" element={<RequireAuth><Student /></RequireAuth>} />
      <Route path="/a/:assignmentId/practice" element={<RequireAuth><Practice /></RequireAuth>} />
      <Route path="/a/:assignmentId/students/:submissionId/practice" element={<RequireAuth><Practice /></RequireAuth>} />
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
