import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { apiFetch, getToken } from '../../lib/auth'

type VerificationState = 'pending' | 'ok' | 'fail'

interface RequireAuthProps {
  children: ReactNode
}

export function RequireAuth({ children }: RequireAuthProps) {
  const initialToken = getToken()
  const [verified, setVerified] = useState<VerificationState>(
    initialToken ? 'pending' : 'fail'
  )
  const location = useLocation()

  useEffect(() => {
    if (!initialToken) return
    let cancelled = false
    apiFetch('/api/auth/me')
      .then((response) => {
        if (cancelled) return
        if (response.ok) {
          setVerified('ok')
        } else {
          setVerified('fail')
        }
      })
      .catch(() => {
        if (cancelled) return
        setVerified('fail')
      })
    return () => {
      cancelled = true
    }
  }, [initialToken])

  if (verified === 'fail') {
    const from = `${location.pathname}${location.search}`
    // For the default landing route, redirect to bare /login — no ?from= noise.
    const isDefault = location.pathname === '/app' && !location.search
    const target = isDefault ? '/login' : `/login?from=${encodeURIComponent(from)}`
    return <Navigate to={target} replace />
  }

  if (verified === 'pending') {
    return null
  }

  return <>{children}</>
}
