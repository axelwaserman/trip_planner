import { Navigate, Route, Routes } from 'react-router-dom'
import { ChatInterface } from './components/ChatInterface'
import { RequireAuth } from './components/auth/RequireAuth'
import { Login } from './pages/Login'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <ChatInterface />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
