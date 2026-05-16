/**
 * Tests for the providerErrors module — Plan 03 creates
 * `frontend/src/lib/providerErrors.ts` exporting mapProbeError + PROVIDERS_FETCH_FAILED.
 *
 * F1-F4 copy mappings (UI-SPEC):
 *   F1 provider_unreachable    → message+hint from backend, inlineCode: ['ollama serve'] (ollama only)
 *   F2 model_not_installed     → inlineCode: [model, `ollama pull <model>`]
 *   F3 missing_api_key         → inlineCode: [`<PROVIDER>_API_KEY`]
 *   F4 providers_fetch_failed  → "Couldn't load providers" + empty inlineCode array
 */

import { describe, expect, it } from 'vitest'
import {
  mapProbeError,
  PROVIDERS_FETCH_FAILED,
  type BackendProbeError,
} from '../providerErrors'

describe('providerErrors', () => {
  it('mapProbeError returns F1 copy with `ollama serve` inlineCode for provider_unreachable on ollama', () => {
    // Arrange
    const body: BackendProbeError = {
      error: 'provider_unreachable',
      message: "Can't reach Ollama at http://localhost:11434",
      hint: 'Run `ollama serve`',
    }

    // Act
    const view = mapProbeError(body, { provider: 'ollama', model: 'qwen3:4b' })

    // Assert
    expect(view.code).toBe('provider_unreachable')
    expect(view.message).toBe(body.message)
    expect(view.hint).toBe(body.hint)
    expect(view.inlineCode).toEqual(['ollama serve'])
  })

  it('mapProbeError omits the ollama snippet for provider_unreachable on a non-ollama provider', () => {
    const body: BackendProbeError = {
      error: 'provider_unreachable',
      message: "Can't reach OpenAI",
      hint: 'Check your network connectivity.',
    }

    const view = mapProbeError(body, { provider: 'openai', model: 'gpt-4o-mini' })

    expect(view.code).toBe('provider_unreachable')
    expect(view.inlineCode).toEqual([])
  })

  it('mapProbeError returns F2 copy with model name and `ollama pull <model>` inlineCode for model_not_installed', () => {
    // Arrange
    const body: BackendProbeError = {
      error: 'model_not_installed',
      message: "Model qwen3:4b isn't installed",
      hint: 'Run `ollama pull qwen3:4b`',
    }

    // Act
    const view = mapProbeError(body, { provider: 'ollama', model: 'qwen3:4b' })

    // Assert
    expect(view.code).toBe('model_not_installed')
    expect(view.inlineCode).toEqual(['qwen3:4b', 'ollama pull qwen3:4b'])
  })

  it('mapProbeError returns F3 copy with the matching ENV_VAR inlineCode for missing_api_key', () => {
    // Arrange
    const body: BackendProbeError = {
      error: 'missing_api_key',
      message: 'OPENAI_API_KEY is not set',
      hint: 'Set OPENAI_API_KEY in your environment.',
    }

    // Act
    const view = mapProbeError(body, { provider: 'openai', model: 'gpt-4o-mini' })

    // Assert
    expect(view.code).toBe('missing_api_key')
    expect(view.inlineCode).toEqual(['OPENAI_API_KEY'])
  })

  it('PROVIDERS_FETCH_FAILED has code providers_fetch_failed and empty inlineCode array', () => {
    expect(PROVIDERS_FETCH_FAILED.code).toBe('providers_fetch_failed')
    expect(PROVIDERS_FETCH_FAILED.inlineCode).toEqual([])
    expect(PROVIDERS_FETCH_FAILED.message).toBe("Couldn't load providers.")
    expect(PROVIDERS_FETCH_FAILED.hint).toBe('Check that the backend is running.')
  })

  it('mapProbeError preserves the backend hint string in the ProviderErrorView output', () => {
    // Arrange
    const body: BackendProbeError = {
      error: 'provider_unreachable',
      message: 'A',
      hint: 'specific actionable hint string from backend',
    }

    // Act
    const view = mapProbeError(body, { provider: 'ollama', model: 'qwen3:4b' })

    // Assert
    expect(view.hint).toBe('specific actionable hint string from backend')
  })
})
