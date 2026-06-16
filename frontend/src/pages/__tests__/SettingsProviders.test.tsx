/**
 * Vitest spec for SettingsProviders page.
 *
 * Plan 08 final polish (2026-05-17):
 *   - Settings page renders only the Ollama card (OpenAI/Anthropic dropped
 *     pending a real Test-connection probe).
 *   - On mount, the page calls GET /api/providers and merges the live
 *     ollama.models discovery list into the rendered card.
 *   - Intro copy was shortened to "We never store your keys on our servers."
 *
 * Behaviour the spec asserts:
 *   1. Renders ONE provider card (Ollama). NOT OpenAI / Anthropic / LM Studio.
 *   2. Renders the "Providers" display heading and "SETTINGS" eyebrow.
 *   3. Renders the short honest intro paragraph.
 *   4. Clicking "Use this provider" writes to 'provider_settings' localStorage.
 *   5. Clicking "Use this provider" navigates to /app.
 *   6. The live /api/providers discovery list is shown as informational chips.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ChakraProvider } from '@chakra-ui/react'
import { system } from '../../theme'
import { SettingsProviders } from '../SettingsProviders'

function mockProvidersFetch(ollamaModels: string[] = []) {
  // Plan 06-05a discriminated ProviderInfoResponse shape: local entries
  // (ollama, lmstudio) carry `type: "local"` + a required `base_url`; cloud
  // entries (openai, anthropic) carry `type: "cloud"` + `api_key_configured`.
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () =>
      Promise.resolve({
        ollama: {
          type: 'local',
          available: true,
          models: ollamaModels,
          base_url: 'http://localhost:11434',
        },
        lmstudio: {
          type: 'local',
          available: false,
          models: [],
          base_url: 'http://localhost:1234/v1',
        },
        openai: {
          type: 'cloud',
          available: false,
          models: [],
          api_key_configured: false,
        },
        anthropic: {
          type: 'cloud',
          available: false,
          models: [],
          api_key_configured: false,
        },
      }),
  })
}

function renderWithProviders(initialPath = '/settings/providers') {
  return render(
    <ChakraProvider value={system}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/settings/providers" element={<SettingsProviders />} />
          <Route path="/app" element={<div>Chat surface</div>} />
        </Routes>
      </MemoryRouter>
    </ChakraProvider>
  )
}

describe('SettingsProviders', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', mockProvidersFetch())
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders the Ollama and LM Studio cards (cloud cards still deferred)', () => {
    // Plan 08b: LM Studio joins the page as the second local card. OpenAI /
    // Anthropic remain deferred until a real Test-connection probe lands —
    // the orchestrator note for this plan calls out the `Test connection`
    // surface as out of scope while the cloud cards are not rendered.
    renderWithProviders()
    expect(screen.getByRole('heading', { name: 'Ollama', level: 2 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /LM Studio/i, level: 2 })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /OpenAI/i, level: 2 })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Anthropic/i, level: 2 })).not.toBeInTheDocument()
  })

  it('renders the Providers display heading and SETTINGS eyebrow', () => {
    renderWithProviders()
    expect(screen.getByRole('heading', { name: 'Providers', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('SETTINGS')).toBeInTheDocument()
  })

  it('renders the short honest intro paragraph', () => {
    renderWithProviders()
    expect(screen.getByText(/We never store your keys on our servers/i)).toBeInTheDocument()
  })

  it('clicking Use this provider writes to provider_settings localStorage', () => {
    const setItemSpy = vi.spyOn(localStorage, 'setItem')
    renderWithProviders()

    // Plan 08b: two cards now render — the Ollama card's Save button is the
    // first match; pick it explicitly so the test stays stable as more
    // providers come back.
    const buttons = screen.getAllByRole('button', { name: /Use this provider/i })
    fireEvent.click(buttons[0])

    const calls = setItemSpy.mock.calls.filter((call) => call[0] === 'provider_settings')
    expect(calls.length).toBeGreaterThan(0)
    const persisted = JSON.parse(calls[calls.length - 1][1] as string)
    expect(persisted.selected.provider).toBe('ollama')
    expect(persisted.ollama).toBeDefined()
  })

  it('clicking Use this provider navigates to /app', () => {
    renderWithProviders()

    const buttons = screen.getAllByRole('button', { name: /Use this provider/i })
    fireEvent.click(buttons[0])

    expect(screen.getByText('Chat surface')).toBeInTheDocument()
  })

  it('shows the live discovered Ollama models as informational chips', async () => {
    vi.stubGlobal('fetch', mockProvidersFetch(['qwen3:4b', 'llama3:8b', 'mistral']))
    renderWithProviders()
    await waitFor(() => {
      expect(screen.getByText('qwen3:4b')).toBeInTheDocument()
      expect(screen.getByText('llama3:8b')).toBeInTheDocument()
      expect(screen.getByText('mistral')).toBeInTheDocument()
    })
  })

  it('reads existing provider_settings from localStorage on mount (Ollama Base URL field is populated)', () => {
    const existing = {
      selected: { provider: 'ollama', model: 'qwen3:4b' },
      ollama: { base_url: 'http://localhost:9999', model: 'qwen3:4b', models: [] },
      openai: { api_key: '', model: 'gpt-4o-mini' },
      anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
    }
    localStorage.setItem('provider_settings', JSON.stringify(existing))

    renderWithProviders()
    // Two Base URL fields now render (Ollama + LM Studio). The Ollama input
    // is the first; assert by index so the test stays stable.
    const baseUrlInputs = screen.getAllByLabelText('Base URL') as HTMLInputElement[]
    expect(baseUrlInputs[0].value).toBe('http://localhost:9999')
  })

  it('back-fills the missing lmstudio entry when existing user data lacks it (Plan 08b migration)', () => {
    // Simulate a Plan 08-era localStorage state that predates the lmstudio
    // entry. The shared loadProviderSettings helper deep-merges with defaults
    // so the lmstudio entry is restored without losing existing user data.
    const existing = {
      selected: { provider: 'ollama', model: 'qwen3:4b' },
      ollama: { base_url: 'http://localhost:11434', model: 'qwen3:4b', models: [] },
      openai: { api_key: 'sk-existing', model: 'gpt-4o-mini' },
      anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
    }
    localStorage.setItem('provider_settings', JSON.stringify(existing))

    renderWithProviders()

    const persisted = JSON.parse(localStorage.getItem('provider_settings') ?? '{}')
    expect(persisted.lmstudio).toBeDefined()
    expect(persisted.lmstudio.base_url).toBe('http://localhost:1234/v1')
    expect(persisted.openai.api_key).toBe('sk-existing')
  })

  it('LM Studio card does NOT render an API Key field', () => {
    renderWithProviders()
    // The LM Studio card has a Base URL field but no API Key field. We assert
    // the heading exists and the page-wide API Key label query returns nothing.
    expect(screen.getByRole('heading', { name: /LM Studio/i, level: 2 })).toBeInTheDocument()
    expect(screen.queryByLabelText('API Key')).not.toBeInTheDocument()
  })

  it('Refresh models button is rendered for both Ollama and LM Studio cards', () => {
    renderWithProviders()
    // Each local card surfaces a "Refresh models" button consuming POST
    // /api/providers/refresh (Plan 06b output, wired by useProviderRefresh).
    const refreshButtons = screen.getAllByRole('button', { name: /Refresh models/i })
    expect(refreshButtons.length).toBe(2)
  })
})
