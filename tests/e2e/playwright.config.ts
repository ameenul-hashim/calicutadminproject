import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1, 
  outputDir: 'test-results',
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['list'],
    ['json', { outputFile: 'playwright-report/results.json' }]
  ],
  use: {
    baseURL: process.env.BASE_URL || 'https://neolearner.onrender.com',
    screenshot: 'on',
    video: 'on',
    trace: 'on',
    actionTimeout: 15000,
    navigationTimeout: 30000,
    launchOptions: {
      slowMo: 1000, // Slow down for visual tracking
    }
  },
  projects: [
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
        headless: false, // Run in headed mode as requested
      },
    },
  ],
});
