import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  timeout: 120_000,
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    video: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Use cached Chromium 1223 to avoid downloading 1228 from network
        launchOptions: {
          executablePath:
            '/Users/axel/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
        },
      },
    },
  ],
})
