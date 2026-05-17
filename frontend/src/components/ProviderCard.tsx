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

import { useMemo, useState } from 'react'
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
import { Eye, EyeOff } from 'lucide-react'

export interface ProviderSettings {
  selected: { provider: string; model: string }
  ollama: { base_url: string; models: string[] }
  openai: { api_key: string; model: string }
  anthropic: { api_key: string; model: string }
}

export type ProviderKind = 'ollama' | 'openai' | 'anthropic'

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

function getMeta(kind: ProviderKind, settings: ProviderSettings): ProviderMeta {
  if (kind === 'ollama') {
    return {
      eyebrow: 'LOCAL',
      displayName: 'Ollama',
      subtitle: 'Open-source models running on your machine. No key needed.',
      models: settings.ollama.models,
      emptyMessage:
        'No models discovered. Run `ollama pull qwen3:4b` then save below to refresh.',
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

  const savedBaseUrl = kind === 'ollama' ? settings.ollama.base_url : ''
  const savedApiKey =
    kind === 'openai'
      ? settings.openai.api_key
      : kind === 'anthropic'
        ? settings.anthropic.api_key
        : ''

  const [baseUrl, setBaseUrl] = useState<string>(savedBaseUrl)
  const [apiKey, setApiKey] = useState<string>(savedApiKey)
  const [showKey, setShowKey] = useState<boolean>(false)

  // Detect Base URL edits that haven't been saved yet — the displayed model
  // list is derived from settings.ollama.models, which only refreshes after a
  // round-trip. Surface that to the user so they don't trust a stale list.
  const baseUrlEdited = useMemo(
    () => kind === 'ollama' && baseUrl.trim() !== savedBaseUrl.trim(),
    [kind, baseUrl, savedBaseUrl]
  )

  // The meta object carries the displayed model list. Recompute on every
  // render so a downstream settings.ollama.models change is reflected in the
  // chip-list without waiting for a remount.
  const meta = getMeta(kind, settings)

  const fieldId = `provider-${kind}`

  // Choose the model to write into the saved selection on Save:
  //  - For Ollama: pick the first discovered model (informational list, not
  //    user-selectable). The chat-header popover is where the user picks.
  //  - For OpenAI / Anthropic: keep the previously-saved model (these cards
  //    aren't rendered today, but the code path is preserved for forward
  //    compat when a future plan re-enables them with a real probe).
  function pickModelOnSave(): string {
    if (kind === 'ollama') {
      const discovered = settings.ollama.models
      if (discovered.length > 0) return discovered[0]
      return settings.selected.model || 'qwen3:4b'
    }
    return kind === 'openai' ? settings.openai.model : settings.anthropic.model
  }

  function handleSave() {
    const model = pickModelOnSave()
    let updated: ProviderSettings
    if (kind === 'ollama') {
      updated = {
        ...settings,
        selected: { provider: 'ollama', model },
        ollama: { base_url: baseUrl, models: settings.ollama.models },
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

        {kind === 'ollama' && (
          <Field.Root>
            <Field.Label htmlFor={`${fieldId}-base-url`}>Base URL</Field.Label>
            <Input
              id={`${fieldId}-base-url`}
              type="url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:11434"
            />
            <Field.HelperText>
              Where the daemon listens. Default works for most local setups.
            </Field.HelperText>
          </Field.Root>
        )}

        {kind === 'ollama' && baseUrlEdited && (
          <Text fontSize="13px" color="fg.secondary">
            The model list below was discovered from the previously saved Base
            URL. Save the new URL to refresh it (live refresh lands in a future
            update).
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

        <Flex justify="flex-end" mt="2">
          <Button colorPalette="accent" onClick={handleSave} type="button">
            Use this provider
          </Button>
        </Flex>
      </Stack>
    </Box>
  )
}
