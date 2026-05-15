/**
 * Failing test stubs for the providerErrors module — Plan 03 will create
 * `frontend/src/lib/providerErrors.ts` exporting mapProbeError + PROVIDERS_FETCH_FAILED.
 *
 * F1-F4 copy mappings (UI-SPEC):
 *   F1 ollama_unreachable      → "Ollama is not reachable" + `ollama serve` inline code
 *   F2 model_not_installed     → "Model <model> isn't installed" + `ollama pull <model>` inline code
 *   F3 missing_api_key         → "<PROVIDER>_API_KEY is not set" + ENV_VAR inline code
 *   F4 providers_fetch_failed  → "Couldn't load providers" + empty inlineCode array
 *
 * Each case is `test.todo` so Vitest reports them as TODO. The executor that
 * lands Plan 03 replaces each with `it(name, () => { ... })`.
 */

import { describe, test } from 'vitest'

describe('providerErrors (Plan 03 will create src/lib/providerErrors.ts)', () => {
  test.todo('mapProbeError returns F1 copy with `ollama serve` inlineCode for ollama_unreachable')
  test.todo(
    'mapProbeError returns F2 copy with model name and `ollama pull <model>` inlineCode for model_not_installed'
  )
  test.todo('mapProbeError returns F3 copy with the matching ENV_VAR inlineCode for missing_api_key')
  test.todo('PROVIDERS_FETCH_FAILED has code providers_fetch_failed and empty inlineCode array')
  test.todo('mapProbeError preserves the backend hint string in the ProviderErrorView output')
})
