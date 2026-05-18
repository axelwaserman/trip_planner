/**
 * Vitest spec for the providerSettings shared module.
 *
 * Covers:
 *   1. cold start → DEFAULT_PROVIDER_SETTINGS, persisted to localStorage.
 *   2. legacy 'llm_provider_config' migration — selected.{provider,model}
 *      carried forward, legacy key removed, new key written.
 *   3. existing 'provider_settings' missing the lmstudio entry → back-filled
 *      with the default lmstudio shape WITHOUT mutating other entries.
 *   4. saveProviderSettings round-trips the full record.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_PROVIDER_SETTINGS,
  loadProviderSettings,
  saveProviderSettings,
  type ProviderSettings,
} from '../providerSettings'

describe('providerSettings', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('loadProviderSettings returns DEFAULT_PROVIDER_SETTINGS when localStorage is empty', () => {
    const result = loadProviderSettings()
    expect(result).toEqual(DEFAULT_PROVIDER_SETTINGS)
    expect(localStorage.getItem('provider_settings')).not.toBeNull()
  })

  it('loadProviderSettings migrates legacy llm_provider_config one-shot', () => {
    localStorage.setItem(
      'llm_provider_config',
      JSON.stringify({ provider: 'ollama', model: 'qwen3:4b' })
    )

    const result = loadProviderSettings()

    expect(localStorage.getItem('llm_provider_config')).toBeNull()
    expect(localStorage.getItem('provider_settings')).not.toBeNull()
    expect(result.selected.provider).toBe('ollama')
    expect(result.selected.model).toBe('qwen3:4b')
    // The lmstudio entry must be present even on a fresh migration so
    // downstream callers don't need null-checks.
    expect(result.lmstudio.base_url).toBe('http://localhost:1234/v1')
  })

  it('loadProviderSettings back-fills the missing lmstudio entry on existing user data', () => {
    // Simulate a Plan 08-era localStorage state: provider_settings exists
    // but predates the lmstudio entry. The user data must NOT be lost.
    const existing = {
      selected: { provider: 'ollama', model: 'qwen3:4b' },
      ollama: { base_url: 'http://localhost:9999', model: 'qwen3:4b', models: ['qwen3:4b'] },
      openai: { api_key: 'sk-existing', model: 'gpt-4o' },
      anthropic: { api_key: 'sk-ant-existing', model: 'claude-3-5-haiku-20241022' },
    }
    localStorage.setItem('provider_settings', JSON.stringify(existing))

    const result = loadProviderSettings()

    expect(result.lmstudio.base_url).toBe('http://localhost:1234/v1')
    expect(result.lmstudio.model).toBe('')
    expect(result.lmstudio.models).toEqual([])
    // Existing entries preserved exactly.
    expect(result.ollama.base_url).toBe('http://localhost:9999')
    expect(result.ollama.models).toEqual(['qwen3:4b'])
    expect(result.openai.api_key).toBe('sk-existing')
    expect(result.openai.model).toBe('gpt-4o')
    expect(result.anthropic.api_key).toBe('sk-ant-existing')

    // The migration was persisted — a re-read sees the full shape.
    const persisted = JSON.parse(
      localStorage.getItem('provider_settings') ?? '{}'
    ) as ProviderSettings
    expect(persisted.lmstudio).toBeDefined()
    expect(persisted.lmstudio.base_url).toBe('http://localhost:1234/v1')
  })

  it('saveProviderSettings writes JSON to provider_settings', () => {
    const sample: ProviderSettings = {
      ...DEFAULT_PROVIDER_SETTINGS,
      ollama: { base_url: 'http://test', model: 'm', models: ['m'] },
    }

    saveProviderSettings(sample)

    const raw = localStorage.getItem('provider_settings')
    expect(raw).not.toBeNull()
    expect(JSON.parse(raw!)).toEqual(sample)
  })
})
