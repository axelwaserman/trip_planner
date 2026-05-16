/**
 * Provider error mapping — maps the backend `ProbeError` body to the
 * `ProviderErrorView` shape that SelectorErrorBanner (Plan 06) renders.
 *
 * F1-F4 copy mappings (UI-SPEC §"Error states"):
 *   F1 provider_unreachable    → message+hint from backend, inlineCode: ['ollama serve'] when ollama
 *   F2 model_not_installed     → inlineCode: [model, `ollama pull <model>`]
 *   F3 missing_api_key         → inlineCode: [`<PROVIDER>_API_KEY`]
 *   F4 providers_fetch_failed  → "Couldn't load providers." + empty inlineCode
 */

export type ProviderErrorCode =
  | 'provider_unreachable'
  | 'model_not_installed'
  | 'missing_api_key'
  | 'providers_fetch_failed'

export interface ProviderErrorView {
  code: ProviderErrorCode
  message: string
  hint: string
  inlineCode: string[]
}

export interface BackendProbeError {
  error: ProviderErrorCode
  message: string
  hint: string
}

interface ProbeContext {
  provider: string
  model: string
}

export function mapProbeError(
  body: BackendProbeError,
  context: ProbeContext
): ProviderErrorView {
  switch (body.error) {
    case 'provider_unreachable':
      return {
        code: 'provider_unreachable',
        message: body.message,
        hint: body.hint,
        // Today only the Ollama probe issues a live HTTP call, so the only
        // actionable shell snippet is `ollama serve`. Cloud providers will
        // surface a different remediation when their live probe lands.
        inlineCode: context.provider === 'ollama' ? ['ollama serve'] : [],
      }
    case 'model_not_installed':
      return {
        code: 'model_not_installed',
        message: body.message,
        hint: body.hint,
        inlineCode: [context.model, `ollama pull ${context.model}`],
      }
    case 'missing_api_key':
      return {
        code: 'missing_api_key',
        message: body.message,
        hint: body.hint,
        inlineCode: [`${context.provider.toUpperCase()}_API_KEY`],
      }
    default:
      return {
        code: 'providers_fetch_failed',
        message: body.message,
        hint: body.hint,
        inlineCode: [],
      }
  }
}

export const PROVIDERS_FETCH_FAILED: ProviderErrorView = {
  code: 'providers_fetch_failed',
  message: "Couldn't load providers.",
  hint: 'Check that the backend is running.',
  inlineCode: [],
}
