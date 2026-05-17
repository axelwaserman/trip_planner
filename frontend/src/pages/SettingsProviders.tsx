/**
 * /settings/providers — the user-facing surface for configuring a provider.
 *
 * Plan 08 final polish (2026-05-17):
 * - Renders ONLY the Ollama card. OpenAI and Anthropic cards were dropped
 *   pending a real Test-connection probe (deferred to a later plan); the
 *   underlying ProviderSettings schema and useChat lib layer still carry the
 *   openai/anthropic entries so the wire contract stays stable.
 * - On mount, fetches GET /api/providers and merges the live ollama.models
 *   discovery list into local settings state — that's the source the card's
 *   informational model list reads from. Lazy-discovery in the backend
 *   guarantees the first call populates the cache.
 *
 * On Save: writes the updated ProviderSettings to localStorage under the
 * 'provider_settings' key (D-21 schema, same key useChat reads at next mount)
 * and navigates to /app. The new useChat mount on /app picks up the new
 * selection and creates a fresh session (D-02).
 */

import { useEffect, useState } from 'react'
import { Box, Grid, GridItem, Heading, Stack, Text } from '@chakra-ui/react'
import { Link, useNavigate } from 'react-router-dom'
import { ProviderCard, type ProviderSettings } from '../components/ProviderCard'
import { apiFetch } from '../lib/auth'

const DEFAULT_PROVIDER_SETTINGS: ProviderSettings = {
  selected: { provider: 'ollama', model: 'qwen3:4b' },
  ollama: { base_url: 'http://localhost:11434', models: [] },
  openai: { api_key: '', model: 'gpt-4o-mini' },
  anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
}

/**
 * Read provider_settings from localStorage; fall back to legacy
 * 'llm_provider_config' (one-shot migration handled by useChat — the page
 * just reads). Returns the default record if neither key is present so the
 * cards render with sensible defaults.
 */
function loadProviderSettings(): ProviderSettings {
  try {
    const raw = localStorage.getItem('provider_settings')
    if (raw) {
      return JSON.parse(raw) as ProviderSettings
    }
    const legacyRaw = localStorage.getItem('llm_provider_config')
    if (legacyRaw) {
      const legacy = JSON.parse(legacyRaw) as { provider: string; model: string }
      return {
        ...DEFAULT_PROVIDER_SETTINGS,
        selected: { provider: legacy.provider, model: legacy.model },
      }
    }
  } catch {
    // Corrupt JSON — fall through to defaults.
  }
  return DEFAULT_PROVIDER_SETTINGS
}

interface ProviderInfo {
  available: boolean
  models: string[]
  base_url: string | null
}
type ProvidersResponse = Record<string, ProviderInfo>

function isProvidersResponse(value: unknown): value is ProvidersResponse {
  if (typeof value !== 'object' || value === null) return false
  // We only care that .ollama exists with a models array — the rest is best-effort.
  const v = value as Record<string, unknown>
  const ollama = v.ollama
  if (typeof ollama !== 'object' || ollama === null) return false
  const models = (ollama as { models?: unknown }).models
  return Array.isArray(models)
}

export function SettingsProviders() {
  const navigate = useNavigate()
  const [settings, setSettings] = useState<ProviderSettings>(() => loadProviderSettings())

  // Discover the live model list from the backend on mount. The backend
  // lazy-runs `factory.refresh_local_models()` on the first call so this
  // hits the daemon at /api/tags, populates the cache, and serves the full
  // list. Falls back silently to the in-localStorage models if the call
  // fails — the card stays usable; an error banner is overkill on a page
  // that already has a working selection.
  useEffect(() => {
    let cancelled = false
    apiFetch('/api/providers')
      .then((response) => {
        if (cancelled || !response.ok) return null
        return response.json() as Promise<unknown>
      })
      .then((payload) => {
        if (cancelled || !payload || !isProvidersResponse(payload)) return
        setSettings((prev) => ({
          ...prev,
          ollama: {
            ...prev.ollama,
            models: payload.ollama.models,
          },
        }))
      })
      .catch(() => {
        // apiFetch handles 401; everything else is non-fatal here.
      })
    return () => {
      cancelled = true
    }
  }, [])

  function handleSave(_kind: 'ollama' | 'openai' | 'anthropic', updated: ProviderSettings) {
    localStorage.setItem('provider_settings', JSON.stringify(updated))
    setSettings(updated)
    navigate('/app')
  }

  return (
    <Grid minH="100dvh" templateColumns={{ base: '1fr', lg: '1fr' }}>
      <GridItem
        bg="bg.canvas"
        px={{ base: '8', lg: '16' }}
        py={{ base: '12', lg: '16' }}
      >
        <Box maxW="640px">
          <Box
            as="span"
            color="accent.solid"
            textTransform="uppercase"
            letterSpacing="0.04em"
            fontSize="13px"
            fontWeight="500"
            mb="6"
            display="inline-block"
          >
            SETTINGS
          </Box>
          <Heading
            as="h1"
            fontFamily="display"
            fontSize="clamp(40px, 4vw + 16px, 48px)"
            lineHeight="0.95"
            letterSpacing="-0.02em"
            color="fg.primary"
          >
            Providers
          </Heading>
          <Text mt="6" maxW="44ch" color="fg.secondary" fontSize="15px" lineHeight="1.5">
            Pick where the agent thinks. We never store your keys on our servers.
          </Text>

          <Stack gap="6" mt="8">
            <ProviderCard kind="ollama" settings={settings} onSave={handleSave} />
          </Stack>

          <Box mt="8">
            <Link
              to="/app"
              style={{
                color: 'var(--chakra-colors-accent-solid)',
                fontSize: '15px',
                textDecoration: 'underline',
                textUnderlineOffset: '4px',
              }}
            >
              Back to chat
            </Link>
          </Box>
        </Box>
      </GridItem>
    </Grid>
  )
}
