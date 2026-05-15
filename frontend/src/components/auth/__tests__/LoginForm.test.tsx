/**
 * Failing test stubs for the LoginForm component — Plan 05 will create
 * `frontend/src/components/auth/LoginForm.tsx`.
 *
 * Each case is `test.todo` so Vitest reports them as TODO (not FAIL). Imports for
 * not-yet-installed packages (react-router-dom) and not-yet-existing modules are
 * intentionally omitted — the executor that lands Plan 05 must add them along
 * with the assertion bodies.
 *
 * D-05 contract referenced in plan 04.2-CONTEXT: LoginForm uses bare `fetch` (not
 * `apiFetch`) for POST /api/auth/token because no token is available at login time.
 */

import { beforeEach, describe, test, vi } from 'vitest'

describe('LoginForm (Plan 05 will create src/components/auth/LoginForm.tsx)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  test.todo('LoginForm renders username and password fields with a Sign in button')
  test.todo('LoginForm calls POST /api/auth/token with form-urlencoded body on submit')
  test.todo('LoginForm stores access_token in localStorage and navigates to / on 200 response')
  test.todo('LoginForm renders inline error "Username or password is incorrect." on 400 response')
  test.todo('LoginForm navigates to ?from= path after successful login when query param present')
  test.todo('Password field toggles between type=password and type=text when eye icon is clicked')
  test.todo('LoginForm uses bare fetch (not apiFetch) for POST /api/auth/token (no token at login time — D-05)')
})
