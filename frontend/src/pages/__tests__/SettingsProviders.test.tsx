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
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () =>
      Promise.resolve({
        ollama: { available: true, models: ollamaModels, base_url: 'http://localhost:11434' },
        lmstudio: { available: false, models: [], base_url: null },
        openai: { available: false, models: [], base_url: null },
        anthropic: { available: false, models: [], base_url: null },
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

  it('renders only the Ollama card (no OpenAI / Anthropic / LM Studio)', () => {
    renderWithProviders()
    expect(screen.getByRole('heading', { name: 'Ollama', level: 2 })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /OpenAI/i, level: 2 })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Anthropic/i, level: 2 })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /LM Studio/i, level: 2 })).not.toBeInTheDocument()
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

    const button = screen.getByRole('button', { name: /Use this provider/i })
    fireEvent.click(button)

    const calls = setItemSpy.mock.calls.filter((call) => call[0] === 'provider_settings')
    expect(calls.length).toBeGreaterThan(0)
    const persisted = JSON.parse(calls[calls.length - 1][1] as string)
    expect(persisted.selected.provider).toBe('ollama')
    expect(persisted.ollama).toBeDefined()
  })

  it('clicking Use this provider navigates to /app', () => {
    renderWithProviders()

    const button = screen.getByRole('button', { name: /Use this provider/i })
    fireEvent.click(button)

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

  it('reads existing provider_settings from localStorage on mount (Base URL field is populated)', () => {
    const existing = {
      selected: { provider: 'ollama', model: 'qwen3:4b' },
      ollama: { base_url: 'http://localhost:9999', models: [] },
      openai: { api_key: '', model: 'gpt-4o-mini' },
      anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
    }
    localStorage.setItem('provider_settings', JSON.stringify(existing))

    renderWithProviders()
    const baseUrlInput = screen.getByLabelText('Base URL') as HTMLInputElement
    expect(baseUrlInput.value).toBe('http://localhost:9999')
  })
})
