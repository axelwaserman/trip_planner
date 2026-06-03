/**
 * SSE smoke pack — every available provider/model permutation must produce a
 * non-error event stream end-to-end.
 *
 * This is the test that would have caught the Ollama `/v1` 404 bug
 * (commit e21a7e3): the provider hands the agent a base_url that PydanticAI
 * forwards verbatim to AsyncOpenAI, and the chat turn 404s before any token
 * is emitted. The only client-side signal is an SSE error frame; an LLM-
 * agnostic assertion ("the stream contains a non-error frame within 90s")
 * catches the bug regardless of which provider is broken.
 *
 * Auto-discovery: providers come from `/api/providers`; only providers with
 * `available: true` and at least one listed model are exercised. Unavailable
 * providers (cloud, missing api key) are skipped — not failed — so the same
 * smoke pack runs on a laptop with Ollama-only and on CI with cloud keys
 * loaded.
 */

import { test, expect } from '@playwright/test'

import {
  createSession,
  firstError,
  frameTypes,
  listProviders,
  login,
  streamChat,
} from '../lib/api'

const PROMPT = 'Reply with exactly one word: hi'
const TOOL_PROMPT = 'Find flights JFK to LAX on 2026-07-15. Use the search_flights tool.'

const LOCAL_PROVIDERS = new Set(['ollama', 'lmstudio'])

type ProviderModel = { provider: string; model: string }

async function discoverPermutations(token: string, request: import('@playwright/test').APIRequestContext): Promise<ProviderModel[]> {
  const providers = await listProviders(request, token)
  const out: ProviderModel[] = []
  for (const [provider, info] of Object.entries(providers)) {
    if (!info.available) continue
    if (!LOCAL_PROVIDERS.has(provider) && !process.env.PLAYWRIGHT_INCLUDE_CLOUD) continue
    for (const model of info.models) {
      out.push({ provider, model })
    }
  }
  return out
}

test.describe('SSE smoke — provider/model matrix', () => {
  test.describe.configure({ mode: 'serial' })

  test('every available local provider/model streams a non-error frame', async ({ request }) => {
    test.setTimeout(900_000) // 15 min for full local matrix
    const session = await login(request)
    const matrix = await discoverPermutations(session.token, request)

    expect(matrix.length, 'at least one local provider must be available').toBeGreaterThan(0)

    const failures: { provider: string; model: string; reason: string }[] = []

    for (const { provider, model } of matrix) {
      const chat = await createSession(request, session.token, provider, model)
      const { frames, raw } = await streamChat(request, session.token, chat.sessionId, PROMPT)

      const types = frameTypes(frames)
      const err = firstError(frames)

      if (err) {
        failures.push({
          provider,
          model,
          reason: `error frame: ${JSON.stringify(err.payload)}`,
        })
        continue
      }

      const hasUseful = types.some((t) => t === 'content' || t === 'thinking')
      if (!hasUseful) {
        failures.push({
          provider,
          model,
          reason: `no content/thinking frames in ${types.length} frames; raw head: ${raw.slice(0, 400)}`,
        })
      }
    }

    if (failures.length > 0) {
      const lines = failures.map((f) => `  - ${f.provider} / ${f.model}: ${f.reason}`)
      throw new Error(`SSE smoke failed for ${failures.length} permutation(s):\n${lines.join('\n')}`)
    }
  })

  test('default provider drives a tool_call → tool_result → content cycle', async ({ request }) => {
    test.setTimeout(300_000)
    const session = await login(request)
    const providers = await listProviders(request, session.token)

    // Pick a qwen3 model in the 8b–9b sweet spot. 4b is too weak at tool
    // selection; 14b+ generates slowly enough on a CPU/MPS-only laptop
    // that the daemon often closes the SSE connection mid-stream. The
    // size order below is "fastest reliable first".
    const SIZE_ORDER = ['8b', '9b', '14b', '27b']
    const candidates: { provider: string; model: string; size: string }[] = []
    for (const [provider, info] of Object.entries(providers)) {
      if (!info.available || !LOCAL_PROVIDERS.has(provider)) continue
      for (const model of info.models) {
        for (const size of SIZE_ORDER) {
          if (model.includes(size)) {
            candidates.push({ provider, model, size })
            break
          }
        }
      }
    }
    candidates.sort((a, b) => SIZE_ORDER.indexOf(a.size) - SIZE_ORDER.indexOf(b.size))

    test.skip(candidates.length === 0, 'no qwen3 8b+ model available locally — tool-cycle assertion needs a model that reliably picks tools')

    const { provider, model } = candidates[0]
    let chat: Awaited<ReturnType<typeof createSession>>
    try {
      chat = await createSession(request, session.token, provider, model)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      if (message.includes('502') && message.includes('provider_unreachable')) {
        test.skip(true, `provider ${provider} went unreachable mid-test — environment issue, not a regression: ${message}`)
        return
      }
      throw err
    }
    const { frames } = await streamChat(request, session.token, chat.sessionId, TOOL_PROMPT)

    const types = frameTypes(frames)
    const err = firstError(frames)
    expect(err, `error frame on ${provider}/${model}: ${JSON.stringify(err?.payload)}`).toBeUndefined()

    expect(types, `tool_call must appear on ${provider}/${model}`).toContain('tool_call')
    expect(types, `tool_result must follow tool_call on ${provider}/${model}`).toContain('tool_result')
    expect(types, `final content must follow tool_result on ${provider}/${model}`).toContain('content')

    const callIdx = types.indexOf('tool_call')
    const resultIdx = types.indexOf('tool_result')
    const contentIdx = types.lastIndexOf('content')
    expect(resultIdx, 'tool_result after tool_call').toBeGreaterThan(callIdx)
    expect(contentIdx, 'final content after tool_result').toBeGreaterThan(resultIdx)
  })
})
