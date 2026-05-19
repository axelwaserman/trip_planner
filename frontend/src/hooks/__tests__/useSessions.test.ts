/**
 * Vitest spec for the useSessions hook.
 *
 * Covers the four contract behaviors:
 *   1. Calls GET /api/chat/sessions on mount (with apiFetch's auth header path).
 *   2. Parses {sessions: [...]} on a 200 response.
 *   3. Sets a non-null error on a non-2xx response.
 *   4. refetch() re-runs the request.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useSessions } from '../useSessions'

function mockSessionsFetch(
  body: unknown = { sessions: [] },
  ok: boolean = true,
  status: number = 200
) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  })
}

describe('useSessions', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('calls /api/chat/sessions on mount', async () => {
    const fetchMock = mockSessionsFetch()
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useSessions())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chat/sessions',
        expect.any(Object)
      )
    })
  })

  it('returns parsed sessions on a 200 response', async () => {
    const fetchMock = mockSessionsFetch({
      sessions: [
        {
          session_id: 's1',
          created_at: '2026-05-17T00:00:00Z',
          provider: 'ollama',
          model: 'qwen3:4b',
          first_message_preview: 'Hello',
        },
      ],
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSessions())

    await waitFor(() => {
      expect(result.current.sessions.length).toBe(1)
      expect(result.current.sessions[0].session_id).toBe('s1')
      expect(result.current.sessions[0].first_message_preview).toBe('Hello')
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('sets a non-null error on a non-2xx response', async () => {
    const fetchMock = mockSessionsFetch({}, false, 500)
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSessions())

    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('refetch re-runs the request', async () => {
    const fetchMock = mockSessionsFetch()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useSessions())

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    act(() => {
      result.current.refetch()
    })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })
  })
})
