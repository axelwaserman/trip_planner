/**
 * useProviderRefresh — calls POST /api/providers/refresh (Plan 06b output)
 * to re-discover Ollama and LM Studio model lists, then updates the saved
 * provider_settings localStorage entry with the freshly-discovered models.
 *
 * Behavior:
 *   - On call: setIsRefreshing(true), apiFetch POST /api/providers/refresh.
 *   - On 2xx: parse {providers: {ollama: {models, available}, lmstudio: {...}}},
 *     load current ProviderSettings, splice the matching provider's models
 *     list into the record, save back to localStorage.
 *   - On 4xx/5xx: parse a ProbeError body via mapProbeError and surface
 *     through `error`.
 *   - Network errors: surface a `providers_fetch_failed` view.
 *   - finally setIsRefreshing(false).
 *
 * Cloud providers (openai, anthropic) don't have a Refresh button — the
 * backend rejects them at the /test endpoint, and there's no discovery
 * step (curated static lists). The hook signature only accepts local
 * provider names.
 */

import { useCallback, useState } from 'react'
import { apiFetch } from '../lib/auth'
import {
  mapProbeError,
  type BackendProbeError,
  type ProviderErrorView,
} from './../lib/providerErrors'
import {
  loadProviderSettings,
  saveProviderSettings,
} from '../lib/providerSettings'

export type LocalProvider = 'ollama' | 'lmstudio'

interface RefreshEntry {
  name: string
  models: string[]
  available: boolean
}

interface RefreshResponse {
  providers: RefreshEntry[]
}

function isRefreshResponse(value: unknown): value is RefreshResponse {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return Array.isArray(v.providers)
}

function isProbeErrorBody(value: unknown): value is BackendProbeError {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.error === 'string' &&
    typeof v.message === 'string' &&
    typeof v.hint === 'string'
  )
}

export interface UseProviderRefreshResult {
  refresh: (provider: LocalProvider) => Promise<void>
  isRefreshing: boolean
  error: ProviderErrorView | null
}

const NETWORK_ERROR_VIEW: ProviderErrorView = {
  code: 'providers_fetch_failed',
  message: "Couldn't reach the server.",
  hint: 'Try again in a moment.',
  inlineCode: [],
}

export function useProviderRefresh(): UseProviderRefreshResult {
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false)
  const [error, setError] = useState<ProviderErrorView | null>(null)

  const refresh = useCallback(async (provider: LocalProvider): Promise<void> => {
    setIsRefreshing(true)
    setError(null)
    try {
      const response = await apiFetch('/api/providers/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })

      if (!response.ok) {
        try {
          const body: unknown = await response.json()
          if (isProbeErrorBody(body)) {
            setError(mapProbeError(body, { provider, model: '' }))
            return
          }
        } catch {
          // Body wasn't JSON — fall through.
        }
        setError(NETWORK_ERROR_VIEW)
        return
      }

      const body: unknown = await response.json()
      if (!isRefreshResponse(body)) {
        setError(NETWORK_ERROR_VIEW)
        return
      }

      const entry = body.providers.find((e) => e.name === provider)
      if (!entry) {
        // Backend response missing the provider entry — treat as soft error
        // so the UI surfaces a hint instead of silently keeping stale data.
        setError(NETWORK_ERROR_VIEW)
        return
      }

      const settings = loadProviderSettings()
      if (provider === 'ollama') {
        settings.ollama = { ...settings.ollama, models: entry.models }
      } else {
        settings.lmstudio = { ...settings.lmstudio, models: entry.models }
      }
      saveProviderSettings(settings)
    } catch {
      setError(NETWORK_ERROR_VIEW)
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  return { refresh, isRefreshing, error }
}
