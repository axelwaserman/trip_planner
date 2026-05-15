/**
 * Failing test stubs for the UserMenu component — Plan 05 / 06 will create
 * `frontend/src/components/chat/UserMenu.tsx`.
 *
 * D-05 contract referenced in plan 04.2-CONTEXT: logout clears auth_token and
 * navigates to /login.
 *
 * Each case is `test.todo` so Vitest reports them as TODO (not FAIL). The
 * executor that lands the component replaces each with the executable
 * assertion body.
 */

import { describe, test } from 'vitest'

describe('UserMenu (Plan 05/06 will create src/components/chat/UserMenu.tsx)', () => {
  test.todo('UserMenu renders the current username')
  test.todo('UserMenu renders a Sign out button')
  test.todo(
    'UserMenu calls clearToken and navigates to /login when Sign out is clicked (D-05: logout clears auth_token + routes to /login)'
  )
  test.todo('UserMenu opens a dropdown when the avatar/initial is clicked')
  test.todo('UserMenu closes the dropdown after Sign out is clicked')
})
