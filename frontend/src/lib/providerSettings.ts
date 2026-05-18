/**
 * Shared ProviderSettings module — single source of truth for the localStorage
 * 'provider_settings' shape (Phase 4.5 D-21 schema, extended by Plan 08b to
 * include the lmstudio entry).
 *
 * Every per-provider entry carries:
 *   - selected: { provider, model } — the active selection driving useChat.
 *   - ollama / lmstudio: { base_url, model, models } — local providers; models
 *     is the last discovered list, written by useProviderRefresh.
 *   - openai / anthropic: { api_key, model } — cloud providers.
 *
 * Migration paths handled by `loadProviderSettings`:
 *   1. cold start (no key) → returns DEFAULT_PROVIDER_SETTINGS, persists it.
 *   2. legacy 'llm_provider_config' (Phase 4.1/4.2) → builds a fresh
 *      ProviderSettings, removes the legacy key one-shot.
 *   3. existing 'provider_settings' missing the lmstudio entry (the Plan 08
 *      → 08b migration) → deep-merges with defaults so the lmstudio entry is
 *      back-filled non-destructively, persists the merged shape.
 *
 * The merge is one-shot per browser tab — once the back-fill writes, future
 * loads see the full shape and skip the merge.
 */

const STORAGE_KEY = 'provider_settings'
const LEGACY_KEY = 'llm_provider_config'

export interface ProviderSettings {
  selected: {
    provider: 'ollama' | 'lmstudio' | 'openai' | 'anthropic'
    model: string
  }
  ollama: { base_url: string; model: string; models: string[] }
  lmstudio: { base_url: string; model: string; models: string[] }
  openai: { api_key: string; model: string }
  anthropic: { api_key: string; model: string }
}

export const DEFAULT_PROVIDER_SETTINGS: ProviderSettings = {
  selected: { provider: 'ollama', model: 'qwen3:4b' },
  ollama: { base_url: 'http://localhost:11434', model: 'qwen3:4b', models: [] },
  lmstudio: { base_url: 'http://localhost:1234/v1', model: '', models: [] },
  openai: { api_key: '', model: 'gpt-4o-mini' },
  anthropic: { api_key: '', model: 'claude-3-5-sonnet-20241022' },
}

interface PartialProviderSettings {
  selected?: Partial<ProviderSettings['selected']>
  ollama?: Partial<ProviderSettings['ollama']>
  lmstudio?: Partial<ProviderSettings['lmstudio']>
  openai?: Partial<ProviderSettings['openai']>
  anthropic?: Partial<ProviderSettings['anthropic']>
}

/**
 * Deep-merge a parsed (possibly partial) ProviderSettings record with the
 * default shape. Missing per-provider entries (e.g. the lmstudio back-fill)
 * pull from defaults; existing entries pass through. The merge is per-key
 * shallow inside each provider entry — a partial ollama record back-fills
 * any missing field (e.g. `models`) from defaults.
 */
function mergeWithDefaults(parsed: PartialProviderSettings): ProviderSettings {
  return {
    selected: {
      ...DEFAULT_PROVIDER_SETTINGS.selected,
      ...(parsed.selected ?? {}),
    },
    ollama: {
      ...DEFAULT_PROVIDER_SETTINGS.ollama,
      ...(parsed.ollama ?? {}),
    },
    lmstudio: {
      ...DEFAULT_PROVIDER_SETTINGS.lmstudio,
      ...(parsed.lmstudio ?? {}),
    },
    openai: {
      ...DEFAULT_PROVIDER_SETTINGS.openai,
      ...(parsed.openai ?? {}),
    },
    anthropic: {
      ...DEFAULT_PROVIDER_SETTINGS.anthropic,
      ...(parsed.anthropic ?? {}),
    },
  }
}

/**
 * Load provider settings from localStorage with full migration handling.
 *
 * Reads ALWAYS return a complete ProviderSettings — defaults back-fill any
 * missing entries so callers don't need null-checks. The merged record is
 * written back to localStorage so the migration is one-shot.
 */
export function loadProviderSettings(): ProviderSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as PartialProviderSettings
      const merged = mergeWithDefaults(parsed)
      // Write back so the next read sees the full shape and skips the merge.
      // Raw and merged JSON are equal when the stored shape is already
      // complete — the extra setItem is a no-op cost-wise but keeps the
      // migration path simple.
      localStorage.setItem(STORAGE_KEY, JSON.stringify(merged))
      return merged
    }

    const legacyRaw = localStorage.getItem(LEGACY_KEY)
    if (legacyRaw) {
      const legacy = JSON.parse(legacyRaw) as { provider?: string; model?: string }
      const provider = legacy.provider ?? DEFAULT_PROVIDER_SETTINGS.selected.provider
      const model = legacy.model ?? DEFAULT_PROVIDER_SETTINGS.selected.model
      const migrated = mergeWithDefaults({
        selected: {
          provider: provider as ProviderSettings['selected']['provider'],
          model,
        },
      })
      localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated))
      localStorage.removeItem(LEGACY_KEY)
      return migrated
    }
  } catch {
    // Corrupt JSON or storage error — fall through to defaults.
  }

  // Cold start — write defaults so the next caller sees them.
  localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_PROVIDER_SETTINGS))
  return DEFAULT_PROVIDER_SETTINGS
}

/**
 * Persist the full ProviderSettings record to localStorage. Callers should
 * pass the complete merged shape — partial updates should call
 * `loadProviderSettings()` first to obtain the current record, mutate the
 * relevant slice, then call this function.
 */
export function saveProviderSettings(settings: ProviderSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}
