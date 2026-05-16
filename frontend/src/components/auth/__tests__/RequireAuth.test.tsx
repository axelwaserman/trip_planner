/**
 * Failing test stubs for the RequireAuth wrapper — Plan 05 will create
 * `frontend/src/components/auth/RequireAuth.tsx`.
 *
 * Each case is `test.todo` so Vitest reports them as TODO (not FAIL). Imports
 * for not-yet-installed packages (react-router-dom) are intentionally omitted —
 * the executor that lands Plan 05 must add them along with the assertion bodies.
 */

import { beforeEach, describe, test } from 'vitest'

describe('RequireAuth (Plan 05 will create src/components/auth/RequireAuth.tsx)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  test.todo('RequireAuth redirects to /login when no token is stored')
  test.todo('RequireAuth redirects to /login?from=<encoded-path> preserving the original path')
  test.todo('RequireAuth renders children when token is valid and /api/auth/me returns 200')
  test.todo('RequireAuth redirects to /login when /api/auth/me returns 401')
  test.todo('RequireAuth shows a loading state while /api/auth/me is in flight')
})
