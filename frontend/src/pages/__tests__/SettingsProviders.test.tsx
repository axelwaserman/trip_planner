/**
 * Vitest spec for SettingsProviders page (Plan 04.5-08 Task 2).
 *
 * Behaviour the spec asserts:
 *   1. Renders three ProviderCards (Ollama, OpenAI, Anthropic) — NOT LM Studio.
 *   2. Renders the "Providers" display heading and "SETTINGS" eyebrow.
 *   3. Renders the locked intro paragraph.
 *   4. Clicking "Use this provider" on a card writes to the
 *      'provider_settings' localStorage key (D-21 schema, same key useChat reads).
 *   5. Clicking "Use this provider" navigates to /app (D-02: switching provider
 *      creates a new session on next mount).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ChakraProvider } from '@chakra-ui/react'
import { system } from '../../theme'
import { SettingsProviders } from '../SettingsProviders'

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
    vi.restoreAllMocks()
  })

  it('renders three provider cards (Ollama, OpenAI, Anthropic) — not LM Studio', () => {
    renderWithProviders()
    expect(screen.getByRole('heading', { name: 'Ollama', level: 2 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'OpenAI', level: 2 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Anthropic', level: 2 })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /LM Studio/i, level: 2 })).not.toBeInTheDocument()
  })

  it('renders the Providers display heading and SETTINGS eyebrow', () => {
    renderWithProviders()
    expect(screen.getByRole('heading', { name: 'Providers', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('SETTINGS')).toBeInTheDocument()
  })

  it('renders the locked intro paragraph verbatim', () => {
    renderWithProviders()
    // The intro must (a) make the no-storage claim and (b) tell users the
    // key travels to the backend at session start. Earlier copy "Keys you
    // paste here live in this browser only — never on our server." conflated
    // "we don't store" with "we never receive" and was misleading.
    expect(screen.getByText(/We never store your keys/i)).toBeInTheDocument()
    expect(
      screen.getByText(/travel to our backend only when starting a chat session/i)
    ).toBeInTheDocument()
  })

  it('clicking Use this provider on a card writes to provider_settings localStorage', () => {
    // The test-setup.ts shim replaces window.localStorage with a plain object
    // (not a Storage subclass), so spy on the shim instance directly.
    const setItemSpy = vi.spyOn(localStorage, 'setItem')
    renderWithProviders()

    // Click the "Use this provider" button on the first card (Ollama).
    const buttons = screen.getAllByRole('button', { name: /Use this provider/i })
    fireEvent.click(buttons[0])

    const calls = setItemSpy.mock.calls.filter((call) => call[0] === 'provider_settings')
    expect(calls.length).toBeGreaterThan(0)
    const persisted = JSON.parse(calls[calls.length - 1][1] as string)
    expect(persisted.selected.provider).toBe('ollama')
    expect(persisted.ollama).toBeDefined()
    expect(persisted.openai).toBeDefined()
    expect(persisted.anthropic).toBeDefined()
  })

  it('clicking Use this provider navigates to /app', () => {
    renderWithProviders()

    const buttons = screen.getAllByRole('button', { name: /Use this provider/i })
    fireEvent.click(buttons[0])

    expect(screen.getByText('Chat surface')).toBeInTheDocument()
  })

  it('reads existing provider_settings from localStorage on mount', () => {
    const existing = {
      selected: { provider: 'openai', model: 'gpt-4o' },
      ollama: { base_url: 'http://localhost:11434', models: [] },
      openai: { api_key: 'sk-saved', model: 'gpt-4o' },
      anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
    }
    localStorage.setItem('provider_settings', JSON.stringify(existing))

    renderWithProviders()
    // The OpenAI API Key field should be populated with the saved key.
    const openaiInputs = screen.getAllByLabelText('API Key') as HTMLInputElement[]
    // The first API Key field is OpenAI (the page renders Ollama, OpenAI, Anthropic
    // in that order; Ollama has no API Key, so [0] is OpenAI, [1] is Anthropic).
    expect(openaiInputs[0].value).toBe('sk-saved')
  })
})
