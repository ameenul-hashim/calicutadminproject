import { test as baseTest, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

export const test = baseTest.extend({
  page: async ({ page }, use, testInfo) => {
    const consoleLogs: string[] = [];
    const networkErrors: string[] = [];

    page.on('console', (msg) => {
      consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
    });

    page.on('pageerror', (err) => {
      consoleLogs.push(`[PAGE ERROR] ${err.message}`);
    });

    page.on('requestfailed', (request) => {
      networkErrors.push(`[FAILED REQUEST] ${request.method()} ${request.url()} - ${request.failure()?.errorText}`);
    });

    await use(page);

    if (testInfo.status !== testInfo.expectedStatus) {
      const logDir = path.join(testInfo.outputDir, 'logs');
      if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });

      fs.writeFileSync(path.join(logDir, 'console.log'), consoleLogs.join('\n'));
      fs.writeFileSync(path.join(logDir, 'network.log'), networkErrors.join('\n'));
      
      // Also attach to report
      await testInfo.attach('console-logs', { body: consoleLogs.join('\n'), contentType: 'text/plain' });
      await testInfo.attach('network-errors', { body: networkErrors.join('\n'), contentType: 'text/plain' });
    }
  },
});

export { expect } from '@playwright/test';
