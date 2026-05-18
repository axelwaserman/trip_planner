/**
 * Vitest spec for the useProviderRefresh hook.
 *
 * Covers:
 *   1. Calls POST /api/providers/refresh
 *   2. Updates provider_settings.ollama.models on a 200 response
 *   3. Updates provider_settings.lmstudio.models when called with 'lmstudio'
 *   4. Sets a non-null error on a non-2xx response
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useProviderRefresh } from '../useProviderRefresh'
import { DEFAULT_PROVIDER_SETTINGS } from '../../lib/providerSettings'

function mockRefreshFetch(
  body: unknown,
  ok: boolean = true,
  status: number = 200
) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  })
}

describe('useProviderRefresh', () => {
  beforeEach(() => {
    localStorage.clear()
    // Seed localStorage with the full default shape so the load + save
    // round-trip below hits the merge path predictably.
    localStorage.setItem(
      'provider_settings',
      JSON.stringify(DEFAULT_PROVIDER_SETTINGS)
    )
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('calls POST /api/providers/refresh on refresh', async () => {
    const fetchMock = mockRefreshFetch({
      providers: {
        ollama: { models: [], available: false },
        lmstudio: { models: [], available: false },
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useProviderRefresh())

    await act(async () => {
      await result.current.refresh('ollama')
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/providers/refresh',
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('updates provider_settings.ollama.models on a 200 response', async () => {
    const fetchMock = mockRefreshFetch({
      providers: {
        ollama: { models: ['qwen3:4b', 'llama3:8b'], available: true },
        lmstudio: { models: [], available: false },
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useProviderRefresh())

    await act(async () => {
      await result.current.refresh('ollama')
    })

    const persisted = JSON.parse(localStorage.getItem('provider_settings') ?? '{}')
    expect(persisted.ollama.models).toEqual(['qwen3:4b', 'llama3:8b'])
  })

  it('updates provider_settings.lmstudio.models when called with lmstudio', async () => {
    const fetchMock = mockRefreshFetch({
      providers: {
        ollama: { models: [], available: false },
        lmstudio: { models: ['some-lmstudio-model'], available: true },
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useProviderRefresh())

    await act(async () => {
      await result.current.refresh('lmstudio')
    })

    const persisted = JSON.parse(localStorage.getItem('provider_settings') ?? '{}')
    expect(persisted.lmstudio.models).toEqual(['some-lmstudio-model'])
  })

  it('sets a non-null error on a non-2xx response', async () => {
    const fetchMock = mockRefreshFetch({}, false, 500)
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useProviderRefresh())

    await act(async () => {
      await result.current.refresh('ollama')
    })

    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
      expect(result.current.isRefreshing).toBe(false)
    })
  })
})
