import { defineConfig } from '@playwright/test'
import process from 'node:process'

const webPort = process.env.MINDMATE_WEB_PORT ?? '5173'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: `http://127.0.0.1:${webPort}` },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
    url: `http://127.0.0.1:${webPort}`,
    reuseExistingServer: true,
  },
})
