/**
 * Failing test stubs for the SelectorErrorBanner component — Plan 06 will create
 * `frontend/src/components/chat/SelectorErrorBanner.tsx`.
 *
 * Renders danger.muted banner with AlertCircle icon, message, hint, optional
 * inlineCode chips, and a Retry button. aria-live="polite", role="status".
 *
 * Each case is `test.todo` so Vitest reports them as TODO. The executor that
 * lands Plan 06 replaces each with the executable assertion body.
 */

import { describe, test } from 'vitest'

describe('SelectorErrorBanner (Plan 06 will create src/components/chat/SelectorErrorBanner.tsx)', () => {
  test.todo('SelectorErrorBanner renders null when error prop is null')
  test.todo('SelectorErrorBanner renders the error message and a Retry button when error is provided')
  test.todo('SelectorErrorBanner calls onRetry when Retry button is clicked')
  test.todo('SelectorErrorBanner has aria-live=polite and role=status on the container')
  test.todo('SelectorErrorBanner renders inlineCode chips for each entry in error.inlineCode')
})
