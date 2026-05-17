/**
 * /settings/providers — the user-facing surface for picking a provider + model.
 *
 * Renders the editorial header (eyebrow "SETTINGS" + display heading "Providers"
 * + locked intro paragraph) and three ProviderCards (Ollama, OpenAI, Anthropic).
 * LM Studio is OUT of orchestrator scope — it lands in Plan 08b.
 *
 * On Save: writes the updated ProviderSettings to localStorage under the
 * 'provider_settings' key (D-21 schema, same key useChat reads at next mount)
 * and navigates to /app. The new useChat mount on /app picks up the new
 * selection and creates a fresh session (D-02).
 */

import { useState } from 'react'
import { Box, Grid, GridItem, Heading, Stack, Text } from '@chakra-ui/react'
import { Link, useNavigate } from 'react-router-dom'
import { ProviderCard, type ProviderSettings } from '../components/ProviderCard'

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

export function SettingsProviders() {
  const navigate = useNavigate()
  const [settings, setSettings] = useState<ProviderSettings>(() => loadProviderSettings())

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
            Pick where the agent thinks. Local providers run on your machine;
            cloud providers send messages to OpenAI or Anthropic. We never store
            your keys — they live in this browser and travel to our backend only
            when starting a chat session, so the model can authenticate.
          </Text>

          <Stack gap="6" mt="8">
            <ProviderCard kind="ollama" settings={settings} onSave={handleSave} />
            <ProviderCard kind="openai" settings={settings} onSave={handleSave} />
            <ProviderCard kind="anthropic" settings={settings} onSave={handleSave} />
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
