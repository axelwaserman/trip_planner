import { useState } from 'react'
import type { FormEvent } from 'react'
import { Box, Button, Field, IconButton, Input, Stack } from '@chakra-ui/react'
import { ArrowRight, Eye, EyeOff } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { setToken } from '../../lib/auth'

interface TokenResponse {
  access_token: string
  token_type: string
}

function isTokenResponse(value: unknown): value is TokenResponse {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return typeof v.access_token === 'string' && typeof v.token_type === 'string'
}

export function LoginForm() {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setError(null)
    setLoading(true)

    const form = e.currentTarget
    const data = new FormData(form)
    const username = String(data.get('username') ?? '')
    const password = String(data.get('password') ?? '')
    const body = new URLSearchParams({ username, password })

    try {
      const response = await fetch('/api/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      })

      if (response.status === 200) {
        const payload: unknown = await response.json()
        if (!isTokenResponse(payload)) {
          setError('The server returned an unexpected response. Try again.')
          return
        }
        setToken(payload.access_token)
        const from = searchParams.get('from') ?? '/'
        navigate(from, { replace: true })
        return
      }

      if (response.status === 400) {
        setError('Username or password is incorrect.')
        return
      }

      setError('Could not sign in. Try again in a moment.')
    } catch {
      setError('Could not reach the server. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={onSubmit} aria-labelledby="signin-heading">
      <Stack gap="4">
        <Field.Root invalid={!!error}>
          <Field.Label htmlFor="login-username">Username</Field.Label>
          <Input
            id="login-username"
            name="username"
            type="text"
            autoComplete="username"
            required
          />
        </Field.Root>

        <Field.Root invalid={!!error}>
          <Field.Label htmlFor="login-password">Password</Field.Label>
          <Box position="relative">
            <Input
              id="login-password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              required
              pr="40px"
            />
            <IconButton
              type="button"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((v) => !v)}
              variant="ghost"
              size="sm"
              position="absolute"
              right="4px"
              top="50%"
              transform="translateY(-50%)"
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </IconButton>
          </Box>
          {error && (
            <Field.ErrorText role="alert" aria-live="polite">
              {error}
            </Field.ErrorText>
          )}
        </Field.Root>

        <Button
          type="submit"
          loading={loading}
          colorPalette="accent"
          width="100%"
        >
          Sign in
          <ArrowRight size={16} />
        </Button>
      </Stack>
    </form>
  )
}
