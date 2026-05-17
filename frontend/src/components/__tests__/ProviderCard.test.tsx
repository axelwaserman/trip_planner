/**
 * Vitest spec for the ProviderCard component (Plan 04.5-08 Task 1).
 *
 * Behaviour the spec asserts (mirrors UI-SPEC §"ProviderCard"):
 *   1. Ollama variant renders a Base URL field, NO API Key field.
 *   2. OpenAI variant renders an API Key field (type=password), NO Base URL.
 *   3. Anthropic variant renders an API Key field, NO Base URL.
 *   4. The show/hide toggle on the API Key field flips input.type between
 *      password and text.
 *   5. Clicking "Use this provider" calls onSave with the updated
 *      ProviderSettings record (selected.provider/model + per-provider entry).
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
  it('renders Ollama variant with Base URL field and no API Key field', () => {
    renderCard('ollama')
    expect(screen.getByLabelText('Base URL')).toBeInTheDocument()
    expect(screen.queryByLabelText('API Key')).not.toBeInTheDocument()
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

  it('renders the helper copy "Stored in this browser only. Never sent to our server." for cloud providers', () => {
    renderCard('openai')
    expect(
      screen.getByText(/Stored in this browser only\. Never sent to our server\./i)
    ).toBeInTheDocument()
  })

  it('renders the locked Ollama subtitle copy', () => {
    renderCard('ollama')
    expect(
      screen.getByText(/Open-source models running on your machine\. No key needed\./i)
    ).toBeInTheDocument()
  })
})
