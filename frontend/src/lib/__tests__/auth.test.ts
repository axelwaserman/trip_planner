/**
 * Failing test stubs for the auth helper module — Plan 03 will create
 * `frontend/src/lib/auth.ts` exporting getToken / setToken / clearToken / apiFetch.
 *
 * Each case is `test.todo` so Vitest reports them as TODO (not FAIL); collection
 * succeeds without importing the not-yet-existing module. Once Plan 03 lands the
 * module, the executor must replace each `test.todo(name)` with `it(name, async () => { ... })`
 * and supply the assertion body.
 */

import { beforeEach, describe, test, vi } from 'vitest'

describe('auth helper module (Plan 03 will create src/lib/auth.ts)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  test.todo('getToken returns null when localStorage is empty')
  test.todo('setToken stores the value under key auth_token')
  test.todo('clearToken removes auth_token from localStorage')
  test.todo('apiFetch injects Authorization: Bearer header when token is present')
  test.todo('apiFetch does not add Authorization header when token is absent')
  test.todo(
    'apiFetch calls clearToken and redirects to /login?flash=session_expired when response is 401'
  )
  test.todo('apiFetch preserves the original path in ?from= when redirecting to /login on 401')
})
