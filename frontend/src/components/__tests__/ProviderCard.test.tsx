/**
 * Vitest spec for the ProviderCard component.
 *
 * Plan 08 final polish (2026-05-17):
 *   - Settings page renders only the Ollama card. OpenAI / Anthropic kinds
 *     stay in the type union for forward compat (lib layer + backend still
 *     drive them), but the visible cards on /settings/providers are gone
 *     pending a real Test-connection probe.
 *   - The card no longer has a Model dropdown — models render as a read-only
 *     informational chip-list. Active model is picked in the chat-header
 *     popover, not here.
 *
 * Behaviour the spec asserts:
 *   1. Ollama variant renders a Base URL field, NO API Key field, and NO
 *      Model dropdown — the chip-list shows discovered models.
 *   2. OpenAI / Anthropic variants still work (forward compat) — API Key
 *      field with show/hide toggle, type=password, autoComplete=off.
 *   3. Clicking "Use this provider" calls onSave with the updated
 *      ProviderSettings record.
 *   4. Helper copy is the short honest version: "We never store your key
 *      on our servers."
 */

import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChakraProvider } from '@chakra-ui/react'
import { system } from '../../theme'
import { ProviderCard, type ProviderSettings } from '../ProviderCard'

const DEFAULT_SETTINGS: ProviderSettings = {
  selected: { provider: 'ollama', model: 'qwen3:4b' },
  ollama: { base_url: 'http://localhost:11434', models: ['qwen3:4b'] },
  openai: { api_key: '', model: 'gpt-4o-mini' },
  anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
}

function renderCard(
  kind: 'ollama' | 'openai' | 'anthropic',
  overrides: Partial<ProviderSettings> = {},
  onSave: (kind: 'ollama' | 'openai' | 'anthropic', updated: ProviderSettings) => void = vi.fn()
) {
  const settings: ProviderSettings = { ...DEFAULT_SETTINGS, ...overrides }
  return render(
    <ChakraProvider value={system}>
      <ProviderCard kind={kind} settings={settings} onSave={onSave} />
    </ChakraProvider>
  )
}

describe('ProviderCard', () => {
  it('renders Ollama variant with Base URL field, no API Key field, and no Model dropdown', () => {
    renderCard('ollama')
    expect(screen.getByLabelText('Base URL')).toBeInTheDocument()
    expect(screen.queryByLabelText('API Key')).not.toBeInTheDocument()
    // The Model dropdown was removed — models are now a read-only chip-list.
    expect(screen.queryByRole('combobox', { name: /Model/i })).not.toBeInTheDocument()
    expect(screen.getByText(/Available models/i)).toBeInTheDocument()
  })

  it('renders Ollama discovered models as informational chips', () => {
    renderCard('ollama', {
      ollama: { base_url: 'http://localhost:11434', models: ['qwen3:4b', 'llama3:8b', 'mistral'] },
    })
    expect(screen.getByText('qwen3:4b')).toBeInTheDocument()
    expect(screen.getByText('llama3:8b')).toBeInTheDocument()
    expect(screen.getByText('mistral')).toBeInTheDocument()
    expect(
      screen.getByText(/Pick the active model from the badge in the chat header/i)
    ).toBeInTheDocument()
  })

  it('shows the Ollama empty-state hint when no models are discovered', () => {
    renderCard('ollama', {
      ollama: { base_url: 'http://localhost:11434', models: [] },
    })
    expect(
      screen.getByText(/No models discovered\. Run `ollama pull qwen3:4b` then save below/i)
    ).toBeInTheDocument()
  })

  it('renders OpenAI variant with API Key field type=password and no Base URL field', () => {
    renderCard('openai')
    const apiKeyInput = screen.getByLabelText('API Key') as HTMLInputElement
    expect(apiKeyInput).toBeInTheDocument()
    expect(apiKeyInput.type).toBe('password')
    expect(apiKeyInput.getAttribute('autocomplete')).toBe('off')
    expect(screen.queryByLabelText('Base URL')).not.toBeInTheDocument()
  })

  it('renders Anthropic variant with API Key field type=password', () => {
    renderCard('anthropic')
    const apiKeyInput = screen.getByLabelText('API Key') as HTMLInputElement
    expect(apiKeyInput).toBeInTheDocument()
    expect(apiKeyInput.type).toBe('password')
  })

  it('clicking show/hide toggle on API Key field flips input type between password and text', () => {
    renderCard('openai')
    const apiKeyInput = screen.getByLabelText('API Key') as HTMLInputElement
    expect(apiKeyInput.type).toBe('password')

    const toggle = screen.getByRole('button', { name: 'Show API key' })
    fireEvent.click(toggle)
    expect(apiKeyInput.type).toBe('text')

    const hideToggle = screen.getByRole('button', { name: 'Hide API key' })
    fireEvent.click(hideToggle)
    expect(apiKeyInput.type).toBe('password')
  })

  it('clicking Use this provider calls onSave with the updated ProviderSettings shape (Ollama)', () => {
    const onSave = vi.fn()
    renderCard('ollama', {}, onSave)

    const baseUrlInput = screen.getByLabelText('Base URL') as HTMLInputElement
    fireEvent.change(baseUrlInput, { target: { value: 'http://localhost:9000' } })

    const saveButton = screen.getByRole('button', { name: /Use this provider/i })
    fireEvent.click(saveButton)

    expect(onSave).toHaveBeenCalledTimes(1)
    const [kindArg, updatedArg] = onSave.mock.calls[0]
    expect(kindArg).toBe('ollama')
    expect(updatedArg.selected).toEqual({ provider: 'ollama', model: 'qwen3:4b' })
    expect(updatedArg.ollama.base_url).toBe('http://localhost:9000')
  })

  it('clicking Use this provider calls onSave with the updated ProviderSettings shape (OpenAI)', () => {
    const onSave = vi.fn()
    renderCard('openai', {}, onSave)

    const apiKeyInput = screen.getByLabelText('API Key') as HTMLInputElement
    fireEvent.change(apiKeyInput, { target: { value: 'sk-test-12345' } })

    const saveButton = screen.getByRole('button', { name: /Use this provider/i })
    fireEvent.click(saveButton)

    expect(onSave).toHaveBeenCalledTimes(1)
    const [kindArg, updatedArg] = onSave.mock.calls[0]
    expect(kindArg).toBe('openai')
    expect(updatedArg.selected.provider).toBe('openai')
    expect(updatedArg.openai.api_key).toBe('sk-test-12345')
  })

  it('renders the short honest helper copy for cloud providers', () => {
    renderCard('openai')
    // The helper makes the no-server-storage claim only; the longer
    // "travels to backend at session start" framing was dropped per UAT
    // feedback as too verbose.
    expect(
      screen.getByText(/We never store your key on our servers\./i)
    ).toBeInTheDocument()
  })

  it('renders the locked Ollama subtitle copy', () => {
    renderCard('ollama')
    expect(
      screen.getByText(/Open-source models running on your machine\. No key needed\./i)
    ).toBeInTheDocument()
  })
})
