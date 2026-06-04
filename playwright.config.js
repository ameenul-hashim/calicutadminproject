const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 300000,
  expect: {
    timeout: 15000,
  },
  use: {
    headless: false,
    launchOptions: {
      slowMo: 800,
    },
    trace: 'on-first-retry',
    video: 'on',
    screenshot: 'on',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },
  projects: [
    {
      name: 'student',
      testMatch: 'student.flow.spec.js',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'teacher',
      testMatch: 'teacher.flow.spec.js',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'admin',
      testMatch: 'admin.flow.spec.js',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'playwright-report/test-results.json' }],
  ],
  outputDir: 'test-results',
});
