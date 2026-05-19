/**
 * Singleton toaster instance for Phase 4.7 toast notifications.
 *
 * Referenced by CONTEXT.md D-11: non-retryable errors (session_error,
 * stream_error) surface as brief toast messages rather than blocking the UI.
 * Mounted via <Toaster toaster={toaster}> in App.tsx (inside ChakraProvider).
 *
 * Usage: import { toaster } from './lib/toaster'; toaster.create({ title, type, duration })
 */
import { createToaster } from '@chakra-ui/react'

export const toaster = createToaster({ placement: 'top-end', overlap: true })
