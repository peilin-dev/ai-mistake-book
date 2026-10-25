import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import LeaveGuard from './components/LeaveGuard'
import App from './App'
import './theme.css'
import './workspace.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={createBrowserRouter([{ path: '*', element: <><LeaveGuard /><App /></> }])} />
  </React.StrictMode>,
)
