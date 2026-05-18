import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Box, Grid, IconButton, useBreakpointValue } from '@chakra-ui/react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { ChatInterface } from './components/ChatInterface'
import { Sidebar } from './components/Sidebar'
import { RequireAuth } from './components/auth/RequireAuth'
import { Login } from './pages/Login'
import { SettingsProviders } from './pages/SettingsProviders'
import { apiFetch } from './lib/auth'

/**
 * AppShell — wraps /app and /settings/providers in a Sidebar + main grid.
 *
 * Desktop (lg breakpoint): persistent 260px sidebar column on the left,
 * main content fills the remaining `1fr`. Mobile (base): sidebar is hidden
 * by default; an `isMenuOpen` state can be lifted into a hand-rolled
 * fixed overlay (the trigger lives in ChatInterface's mobile header).
 *
 * Username is resolved once at the shell level and passed to Sidebar so
 * the Sidebar doesn't re-fetch /api/auth/me — ChatInterface still keeps
 * its own copy until the badge is redesigned.
 */
function AppShell({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string>('')
  const [isMenuOpen, setIsMenuOpen] = useState<boolean>(false)
  const isMobile = useBreakpointValue({ base: true, lg: false })

  useEffect(() => {
    let cancelled = false
    apiFetch('/api/auth/me')
      .then((response) => {
        if (cancelled || !response.ok) return null
        return response.json() as Promise<unknown>
      })
      .then((payload) => {
        if (cancelled || !payload) return
        if (typeof payload === 'object' && payload !== null && 'username' in payload) {
          const value = (payload as { username: unknown }).username
          if (typeof value === 'string') setUsername(value)
        }
      })
      .catch(() => {
        // 401 already handled by apiFetch; everything else is non-fatal.
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <Grid
        templateColumns={{ base: '1fr', lg: '260px 1fr' }}
        minH="100dvh"
      >
        {/* Desktop persistent sidebar */}
        {!isMobile && (
          <Box>
            <Sidebar username={username} />
          </Box>
        )}
        <Box minW="0">{children}</Box>
      </Grid>

      {/* Mobile hamburger trigger — fixed top-left, hidden on desktop. */}
      {isMobile && !isMenuOpen && (
        <IconButton
          aria-label="Open menu"
          onClick={() => setIsMenuOpen(true)}
          position="fixed"
          top="3"
          left="3"
          zIndex="30"
          variant="ghost"
          size="sm"
          bg="bg.surface"
          borderWidth="1px"
          borderColor="border.subtle"
        >
          <Menu size={20} />
        </IconButton>
      )}

      {/* Mobile overlay — rendered outside the grid so it can sit above the
          main content. Triggered by the hamburger button above. */}
      {isMobile && isMenuOpen && (
        <Box
          position="fixed"
          inset="0"
          zIndex="40"
          display="flex"
        >
          <Sidebar
            username={username}
            onNavigate={() => setIsMenuOpen(false)}
          />
          <Box
            flex="1"
            bg="rgba(0,0,0,0.4)"
            onClick={() => setIsMenuOpen(false)}
            cursor="pointer"
          />
        </Box>
      )}
    </>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/app"
        element={
          <RequireAuth>
            <AppShell>
              <ChatInterface />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/settings/providers"
        element={
          <RequireAuth>
            <AppShell>
              <SettingsProviders />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  )
}

export default App
