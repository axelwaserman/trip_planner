/**
 * ProviderCard — one card per provider on the /settings/providers page.
 *
 * Plan 08 final polish (2026-05-17):
 * - Settings page renders ONLY the Ollama card. OpenAI / Anthropic kinds
 *   remain in the type union for forward compat (the lib layer + backend
 *   still know how to drive them) — the parent page just doesn't render
 *   them today, pending a real Test-connection probe (deferred).
 * - The card NO LONGER shows a Model dropdown. Models are presented as a
 *   read-only informational chip-list. Active model selection happens in
 *   the chat-header quick-switcher popover; the settings page is for
 *   configuring the provider (URL / key) only.
 *
 * UI-SPEC §"ProviderCard" governs layout, colors, and copy. Tokens are pulled
 * from frontend/src/theme/index.ts — no inline OKLCH values are introduced.
 *
 * The component is presentational + form-state-managing only. It does not
 * touch localStorage directly; the parent page does that on `onSave`.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  Box,
  Button,
  Field,
  Flex,
  Heading,
  IconButton,
  Input,
  Stack,
  Text,
  Wrap,
} from '@chakra-ui/react'
import { Eye, EyeOff, RefreshCw } from 'lucide-react'
import { useProviderRefresh } from '../hooks/useProviderRefresh'
import {
  loadProviderSettings,
  type ProviderSettings,
} from '../lib/providerSettings'
import { SelectorErrorBanner } from './chat/SelectorErrorBanner'

// Re-export the canonical ProviderSettings type so existing consumers that
// imported it from ProviderCard (Plan 08-era) keep compiling. The single
// source of truth is `frontend/src/lib/providerSettings.ts`.
export type { ProviderSettings }

export type ProviderKind = 'ollama' | 'lmstudio' | 'openai' | 'anthropic'

export interface ProviderCardProps {
  kind: ProviderKind
  settings: ProviderSettings
  onSave: (kind: ProviderKind, updated: ProviderSettings) => void
}

interface ProviderMeta {
  eyebrow: 'LOCAL' | 'CLOUD'
  displayName: string
  subtitle: string
  models: string[]
  emptyMessage: string | null
}

const OPENAI_MODELS = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1-mini', 'o3-mini']
const ANTHROPIC_MODELS = [
  'claude-3-5-sonnet-20241022',
  'claude-3-5-haiku-20241022',
  'claude-3-opus-20240229',
]

/**
 * Validate a base URL entered by the user for a local provider.
 *
 * Returns null when the URL is valid (or empty — empty means "use the
 * default"), or a human-readable error string when it is not.
 *
 * Mirrors the backend SSRF guard in SessionCreateRequest._validate_base_url
 * so the user gets immediate inline feedback before any network round-trip.
 */
function validateBaseUrl(url: string, kind: ProviderKind): string | null {
  if (url.trim().length === 0) return null
  try {
    const parsed = new URL(url.trim())
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return 'URL must use http or https'
    }
    const allowedHosts = ['localhost', '127.0.0.1', 'host.docker.internal']
    if (!allowedHosts.includes(parsed.hostname)) {
      return 'Only localhost, 127.0.0.1, or host.docker.internal are allowed'
    }
    if (kind === 'ollama' && parsed.pathname !== '/') {
      return 'Ollama URL must be host only (e.g. http://localhost:11434) — no path'
    }
    return null
  } catch {
    return 'Invalid URL format'
  }
}

function getMeta(kind: ProviderKind, settings: ProviderSettings): ProviderMeta {
  if (kind === 'ollama') {
    return {
      eyebrow: 'LOCAL',
      displayName: 'Ollama',
      subtitle: 'Open-source models running on your machine. No key needed.',
      models: settings.ollama.models,
      // Plan 08b: empty-state copy hints at the new Refresh button (Plan 06b
      // POST /api/providers/refresh) which the action row now wires up.
      emptyMessage:
        'No models discovered. Run `ollama pull qwen3:4b` then click Refresh.',
    }
  }
  if (kind === 'lmstudio') {
    return {
      eyebrow: 'LOCAL',
      displayName: 'LM Studio',
      subtitle:
        'Local models exposed over an OpenAI-compatible API. No key needed.',
      models: settings.lmstudio.models,
      emptyMessage:
        'No models loaded. Open LM Studio and load a model, then click Refresh.',
    }
  }
  if (kind === 'openai') {
    return {
      eyebrow: 'CLOUD',
      displayName: 'OpenAI',
      subtitle: 'gpt-4o, gpt-4o-mini, o-series. Bring your own key.',
      models: OPENAI_MODELS,
      emptyMessage: null,
    }
  }
  return {
    eyebrow: 'CLOUD',
    displayName: 'Anthropic',
    subtitle: 'Claude 3.5 Sonnet, Haiku, Opus. Bring your own key.',
    models: ANTHROPIC_MODELS,
    emptyMessage: null,
  }
}

interface StatusPill {
  label: 'Ready' | 'Needs setup'
  bg: string
  color: string
  dotBg: string
}

function deriveStatus(kind: ProviderKind, settings: ProviderSettings): StatusPill {
  // "Ready" when the saved settings have a base_url for local OR a non-empty
  // api_key for cloud. UI-SPEC §"Status pill" — live probing is out of scope
  // for the card itself; the page just reflects the persisted state.
  const ready =
    (kind === 'ollama' && settings.ollama.base_url.trim().length > 0) ||
    (kind === 'lmstudio' && settings.lmstudio.base_url.trim().length > 0) ||
    (kind === 'openai' && settings.openai.api_key.trim().length > 0) ||
    (kind === 'anthropic' && settings.anthropic.api_key.trim().length > 0)

  if (ready) {
    return {
      label: 'Ready',
      bg: 'accent.muted',
      color: 'accent.solid',
      dotBg: 'accent.solid',
    }
  }
  return {
    label: 'Needs setup',
    bg: 'bg.canvas',
    color: 'fg.secondary',
    dotBg: 'border.strong',
  }
}

export function ProviderCard({ kind, settings, onSave }: ProviderCardProps) {
  const status = deriveStatus(kind, settings)

  const isLocal = kind === 'ollama' || kind === 'lmstudio'

  const savedBaseUrl =
    kind === 'ollama'
      ? settings.ollama.base_url
      : kind === 'lmstudio'
        ? settings.lmstudio.base_url
        : ''
  const savedApiKey =
    kind === 'openai'
      ? settings.openai.api_key
      : kind === 'anthropic'
        ? settings.anthropic.api_key
        : ''

  const [baseUrl, setBaseUrl] = useState<string>(savedBaseUrl)
  const [apiKey, setApiKey] = useState<string>(savedApiKey)
  const [showKey, setShowKey] = useState<boolean>(false)
  const [baseUrlError, setBaseUrlError] = useState<string | null>(null)
  // Local mirror of the discovered models list. Initialised from props but
  // updated by the Refresh button so the chip-list reflects the latest
  // discovery without waiting for the parent to re-read localStorage.
  const initialModels =
    kind === 'ollama'
      ? settings.ollama.models
      : kind === 'lmstudio'
        ? settings.lmstudio.models
        : []
  const [localModels, setLocalModels] = useState<string[]>(initialModels)

  // Sync localModels with parent-controlled settings updates. The
  // SettingsProviders page re-fetches GET /api/providers on mount and
  // splices the live discovery list into per-provider entries — that
  // upstream change must reach the chip-list without a remount.
  const upstreamModels =
    kind === 'ollama'
      ? settings.ollama.models
      : kind === 'lmstudio'
        ? settings.lmstudio.models
        : null
  useEffect(() => {
    if (upstreamModels === null) return
    setLocalModels(upstreamModels)
    // We intentionally only sync from props; the Refresh button's
    // localStorage write is read separately by re-loading via
    // loadProviderSettings inside handleRefresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [upstreamModels])

  // Refresh hook for local providers — Plan 06b POST /api/providers/refresh.
  const { refresh, isRefreshing, error: refreshError } = useProviderRefresh()

  // Detect Base URL edits that haven't been saved yet — the displayed model
  // list is derived from settings.{ollama|lmstudio}.models, which only
  // refreshes after a round-trip. Surface that to the user so they don't
  // trust a stale list.
  const baseUrlEdited = useMemo(
    () => isLocal && baseUrl.trim() !== savedBaseUrl.trim(),
    [isLocal, baseUrl, savedBaseUrl]
  )

  // The meta object carries the displayed model list. Recompute on every
  // render so a downstream settings.{ollama|lmstudio}.models change is
  // reflected in the chip-list without waiting for a remount.
  const propsMeta = getMeta(kind, settings)
  const meta: ProviderMeta = isLocal
    ? { ...propsMeta, models: localModels }
    : propsMeta

  const fieldId = `provider-${kind}`

  // Choose the model to write into the saved selection on Save:
  //  - For Ollama / LM Studio: pick the first discovered model (informational
  //    list, not user-selectable). The chat-header popover is where the user
  //    picks.
  //  - For OpenAI / Anthropic: keep the previously-saved model.
  function pickModelOnSave(): string {
    if (kind === 'ollama') {
      const discovered = localModels
      if (discovered.length > 0) return discovered[0]
      return settings.selected.model || 'qwen3:4b'
    }
    if (kind === 'lmstudio') {
      const discovered = localModels
      if (discovered.length > 0) return discovered[0]
      return settings.lmstudio.model || ''
    }
    return kind === 'openai' ? settings.openai.model : settings.anthropic.model
  }

  function handleSave() {
    setBaseUrlError(null)
    if (isLocal && baseUrl.trim().length > 0) {
      const urlErr = validateBaseUrl(baseUrl.trim(), kind)
      if (urlErr) {
        setBaseUrlError(urlErr)
        return
      }
    }
    const model = pickModelOnSave()
    let updated: ProviderSettings
    if (kind === 'ollama') {
      updated = {
        ...settings,
        selected: { provider: 'ollama', model },
        ollama: { base_url: baseUrl, model, models: localModels },
      }
    } else if (kind === 'lmstudio') {
      updated = {
        ...settings,
        selected: { provider: 'lmstudio', model },
        lmstudio: { base_url: baseUrl, model, models: localModels },
      }
    } else if (kind === 'openai') {
      updated = {
        ...settings,
        selected: { provider: 'openai', model },
        openai: { api_key: apiKey, model },
      }
    } else {
      updated = {
        ...settings,
        selected: { provider: 'anthropic', model },
        anthropic: { api_key: apiKey, model },
      }
    }
    onSave(kind, updated)
  }

  async function handleRefresh() {
    if (kind !== 'ollama' && kind !== 'lmstudio') return
    await refresh(kind)
    // Re-read the freshly-saved settings to refresh the local chip-list.
    // useProviderRefresh writes to localStorage on success — pick up the
    // updated entry here so the UI reflects the new model list immediately.
    const fresh = loadProviderSettings()
    if (kind === 'ollama') {
      setLocalModels(fresh.ollama.models)
    } else {
      setLocalModels(fresh.lmstudio.models)
    }
  }

  return (
    <Box
      bg="bg.surface"
      borderWidth="1px"
      borderColor="border.subtle"
      borderRadius="lg"
      p="6"
    >
      <Stack gap="3">
        <Flex justify="space-between" align="flex-start">
          <Box
            as="span"
            color="accent.solid"
            textTransform="uppercase"
            letterSpacing="0.04em"
            fontSize="13px"
            fontWeight="500"
          >
            {meta.eyebrow}
          </Box>
          <Flex
            align="center"
            gap="2"
            bg={status.bg}
            color={status.color}
            borderRadius="full"
            px="3"
            py="1"
            fontSize="13px"
            fontWeight="500"
          >
            <Box
              w="8px"
              h="8px"
              borderRadius="full"
              bg={status.dotBg}
              flexShrink={0}
            />
            {status.label}
          </Flex>
        </Flex>

        <Heading
          as="h2"
          fontFamily="display"
          fontSize="24px"
          lineHeight="1.1"
          letterSpacing="-0.01em"
          color="fg.primary"
        >
          {meta.displayName}
        </Heading>

        <Text fontSize="15px" color="fg.secondary" lineHeight="1.5">
          {meta.subtitle}
        </Text>

        {isLocal && (
          <Field.Root invalid={!!baseUrlError}>
            <Field.Label htmlFor={`${fieldId}-base-url`}>Base URL</Field.Label>
            <Input
              id={`${fieldId}-base-url`}
              type="url"
              value={baseUrl}
              onChange={(e) => {
                setBaseUrl(e.target.value)
                // Clear error as soon as the user starts correcting the value
                if (baseUrlError) setBaseUrlError(null)
              }}
              placeholder={
                kind === 'lmstudio'
                  ? 'http://localhost:1234/v1'
                  : 'http://localhost:11434'
              }
            />
            {baseUrlError ? (
              <Field.ErrorText>{baseUrlError}</Field.ErrorText>
            ) : (
              <Field.HelperText>
                Where the daemon listens. Default works for most local setups.
              </Field.HelperText>
            )}
          </Field.Root>
        )}

        {isLocal && baseUrlEdited && (
          <Text fontSize="13px" color="fg.secondary">
            The model list below was discovered from the previously saved Base
            URL. Click Refresh to re-discover.
          </Text>
        )}

        {(kind === 'openai' || kind === 'anthropic') && (
          <Field.Root>
            <Field.Label htmlFor={`${fieldId}-api-key`}>API Key</Field.Label>
            <Box position="relative">
              <Input
                id={`${fieldId}-api-key`}
                type={showKey ? 'text' : 'password'}
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                pr="40px"
              />
              <IconButton
                type="button"
                aria-label={showKey ? 'Hide API key' : 'Show API key'}
                aria-pressed={showKey}
                onClick={() => setShowKey((v) => !v)}
                variant="ghost"
                size="sm"
                position="absolute"
                right="4px"
                top="50%"
                transform="translateY(-50%)"
              >
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </IconButton>
            </Box>
            <Field.HelperText>
              We never store your key on our servers.
            </Field.HelperText>
          </Field.Root>
        )}

        <Box>
          <Text
            id={`${fieldId}-models`}
            fontSize="14px"
            fontWeight="500"
            color="fg.primary"
            mb="2"
          >
            Available models
          </Text>
          {meta.models.length === 0 ? (
            <Text fontSize="13px" color="fg.secondary" lineHeight="1.5">
              {meta.emptyMessage ?? 'No models available.'}
            </Text>
          ) : (
            <Wrap gap="2" aria-labelledby={`${fieldId}-models`}>
              {meta.models.map((m) => (
                <Box
                  key={m}
                  as="span"
                  bg="bg.canvas"
                  borderWidth="1px"
                  borderColor="border.subtle"
                  borderRadius="full"
                  px="3"
                  py="1"
                  fontSize="13px"
                  fontFamily="mono"
                  color="fg.primary"
                >
                  {m}
                </Box>
              ))}
            </Wrap>
          )}
          <Text fontSize="13px" color="fg.secondary" mt="2">
            Pick the active model from the badge in the chat header.
          </Text>
        </Box>

        {isLocal && (
          <>
            {/* CSS keyframe for the spinning Refresh icon. Defined inline so
                the rule is co-located with the only consumer; the
                @keyframes rule is hoisted to a stylesheet by the browser
                regardless of where the <style> tag is rendered. */}
            <style>{`
              @keyframes provider-card-spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
              }
            `}</style>
            <Flex align="center" gap="3">
              <Button
                variant="ghost"
                colorPalette="accent"
                onClick={() => {
                  void handleRefresh()
                }}
                disabled={isRefreshing}
                type="button"
                size="sm"
              >
                <Box
                  as="span"
                  display="inline-flex"
                  alignItems="center"
                  style={{
                    animation: isRefreshing
                      ? 'provider-card-spin 1s linear infinite'
                      : undefined,
                  }}
                >
                  <RefreshCw size={14} />
                </Box>
                <Box as="span" ml="2">
                  {isRefreshing ? 'Refreshing…' : 'Refresh models'}
                </Box>
              </Button>
            </Flex>
            {refreshError && (
              <SelectorErrorBanner
                error={refreshError}
                onRetry={() => {
                  void handleRefresh()
                }}
              />
            )}
          </>
        )}

        <Flex justify="flex-end" mt="2">
          <Button colorPalette="accent" onClick={handleSave} type="button">
            Use this provider
          </Button>
        </Flex>
      </Stack>
    </Box>
  )
}
