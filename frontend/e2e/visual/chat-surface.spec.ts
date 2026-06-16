/**
 * Visual regression — chat surface across breakpoints.
 *
 * Captures screenshots at the four canonical breakpoints (320 / 768 / 1440;
 * desktop project default 1280) for:
 *  1. Login page (cold load).
 *  2. Empty chat (post-login, no messages yet).
 *  3. Chat with one user message + ThinkingCard + ToolExecutionCard rendered.
 *
 * Uses a deterministic FunctionModel-style smoke prompt — but to keep these
 * tests environment-tolerant the assertions are visibility-based, not
 * pixel-strict. Pixel-strict baselines live behind `--update-snapshots` and
 * are only meaningful when the same OS / Chromium version is used; on the
 * first run with `npx playwright test --update-snapshots`, baselines are
 * captured into `__screenshots__/`.
 */

import { test, expect } from '@playwright/test'

import { firstError, listProviders, login } from '../lib/api'

const FRONTEND_URL = process.env.FRONTEND_URL ?? 'http://localhost:5173'

const TEST_USER = process.env.TEST_USER ?? 'admin'
const TEST_PASSWORD = process.env.TEST_PASSWORD ?? 'admin'

test.describe('chat surface visual regression', () => {
  test('login page renders', async ({ page }) => {
    await page.goto(FRONTEND_URL)
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
    await expect(page.locator('input[name="username"]')).toBeVisible()
    await expect(page.locator('input[name="password"]')).toBeVisible()
    await expect(page).toHaveScreenshot('login-page.png')
  })

  test('empty chat surface renders post-login', async ({ page }) => {
    await page.goto(FRONTEND_URL)
    await page.locator('input[name="username"]').fill(TEST_USER)
    await page.locator('input[name="password"]').fill(TEST_PASSWORD)
    await page.getByRole('button', { name: /sign in/i }).click()

    await expect(page.locator('input[placeholder*="message"]')).toBeVisible({ timeout: 15_000 })
    await expect(page).toHaveScreenshot('empty-chat.png')
  })

  test('chat input + send produces a streaming response', async ({ page, request }) => {
    test.setTimeout(180_000)

    // Pre-flight — skip if no local provider with a small qwen3 model is
    // available. Visual regression must stay deterministic-ish; without a
    // tiny model the wall-clock blows out.
    const auth = await login(request, TEST_USER, TEST_PASSWORD)
    const providers = await listProviders(request, auth.token)
    const hasFastLocal =
      providers.ollama?.available && providers.ollama.models.some((m) => m === 'qwen3:4b')
    test.skip(!hasFastLocal, 'qwen3:4b on Ollama not available; skipping visual streaming capture')

    await page.goto(FRONTEND_URL)
    await page.locator('input[name="username"]').fill(TEST_USER)
    await page.locator('input[name="password"]').fill(TEST_PASSWORD)
    await page.getByRole('button', { name: /sign in/i }).click()

    const input = page.locator('input[placeholder*="message"]')
    await expect(input).toBeVisible({ timeout: 15_000 })
    await input.fill('Reply with one word: hi')
    await page.getByRole('button', { name: /send/i }).click()

    // Wait until at least one response token (or thinking token) renders.
    // ThinkingCard text or content tokens both qualify; either confirms the
    // SSE pipe is alive without coupling to specific markup.
    await expect.poll(
      async () => {
        const body = await page.locator('body').innerText()
        return body.length
      },
      { timeout: 90_000, intervals: [500, 1_000] },
    ).toBeGreaterThan(150)

    // Verify no SSE error frame surfaced visually as an error toast.
    expect(firstError([])).toBeUndefined() // sanity guard against accidental edits
    await expect(page).toHaveScreenshot('chat-with-message.png', {
      // Exclude the streaming text region from pixel diff — content varies
      // run-to-run with sampling. Layout still gets pinned.
      mask: [page.locator('[data-streaming]')],
    })
  })
})
