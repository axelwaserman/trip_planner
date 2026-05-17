/**
 * ProviderCard — one card per provider on the /settings/providers page.
 *
 * Renders three shapes (kind = 'ollama' | 'openai' | 'anthropic'):
 *   - Ollama (LOCAL): Base URL field + Model select.
 *   - OpenAI / Anthropic (CLOUD): API Key field with show/hide toggle + Model select.
 *
 * UI-SPEC §"ProviderCard" governs layout, colors, and copy. Tokens are pulled
 * from frontend/src/theme/index.ts — no inline OKLCH values are introduced.
 *
 * The Refresh and Test connection buttons that UI-SPEC describes are out of
 * scope for Plan 08 (the underlying endpoints land in 08b/later phases).
 *
 * The component is presentational + form-state-managing only. It does not
 * touch localStorage directly; the parent page does that on `onSave`.
 */

import { useState } from 'react'
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
  emptyOption: string | null
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
      emptyOption:
        'No models discovered. Run `ollama pull qwen3:4b`, then refresh in Settings.',
    }
  }
  if (kind === 'openai') {
    return {
      eyebrow: 'CLOUD',
      displayName: 'OpenAI',
      subtitle: 'gpt-4o, gpt-4o-mini, o-series. Bring your own key.',
      models: OPENAI_MODELS,
      emptyOption: null,
    }
  }
  return {
    eyebrow: 'CLOUD',
    displayName: 'Anthropic',
    subtitle: 'Claude 3.5 Sonnet, Haiku, Opus. Bring your own key.',
    models: ANTHROPIC_MODELS,
    emptyOption: null,
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
  const meta = getMeta(kind, settings)
  const status = deriveStatus(kind, settings)

  const [baseUrl, setBaseUrl] = useState<string>(
    kind === 'ollama' ? settings.ollama.base_url : ''
  )
  const [apiKey, setApiKey] = useState<string>(
    kind === 'openai'
      ? settings.openai.api_key
      : kind === 'anthropic'
        ? settings.anthropic.api_key
        : ''
  )
  const [showKey, setShowKey] = useState<boolean>(false)
  const initialModel =
    kind === 'ollama'
      ? settings.ollama.models[0] ?? settings.selected.model
      : kind === 'openai'
        ? settings.openai.model
        : settings.anthropic.model
  const [model, setModel] = useState<string>(initialModel)

  const fieldId = `provider-${kind}`

  function handleSave() {
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
              Stored in this browser only. Never sent to our server.
            </Field.HelperText>
          </Field.Root>
        )}

        <Field.Root>
          <Field.Label htmlFor={`${fieldId}-model`}>Model</Field.Label>
          <Box
            as="select"
            id={`${fieldId}-model`}
            value={model}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
              setModel(e.target.value)
            }
            disabled={meta.models.length === 0}
            w="100%"
            px="3"
            py="2"
            borderRadius="md"
            borderWidth="1px"
            borderColor="border.subtle"
            bg="bg.surface"
            color="fg.primary"
            fontSize="14px"
            fontFamily="body"
          >
            {meta.models.length === 0 && meta.emptyOption ? (
              <option disabled value="">
                {meta.emptyOption}
              </option>
            ) : (
              meta.models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))
            )}
          </Box>
        </Field.Root>

        <Flex justify="flex-end" mt="2">
          <Button colorPalette="accent" onClick={handleSave} type="button">
            Use this provider
          </Button>
        </Flex>
      </Stack>
    </Box>
  )
}
