import { test, expect } from '@playwright/test';
import {
  loginAsStudent,
  loginAsTeacher,
  loginAsAdmin,
  URLS,
} from '../fixtures/auth.fixture';

test.describe('SECURITY TESTS', () => {
  let consoleErrors: string[] = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
  });

  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status !== 'passed') {
      await page.screenshot({
        path: `playwright-report/screenshots/security_${testInfo.title.replace(/\s+/g, '_')}_FAILED.png`,
        fullPage: true,
      });
    }
    testInfo.attachments.push({
      name: `console-errors-${testInfo.title}`,
      contentType: 'text/plain',
      body: Buffer.from(consoleErrors.join('\n')),
    });
  });

  test('[SEC-01] Student cannot access Admin URLs', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.adminLogin);
    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/customadmin/dashboard/');
  });

  test('[SEC-02] Student cannot access Admin Dashboard', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/customadmin/dashboard/');
    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/customadmin/dashboard/');
  });

  test('[SEC-03] Student cannot access Teacher Dashboard', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.teacherDashboard);
    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/teacher/dashboard/');
  });

  test('[SEC-04] Teacher cannot access Admin Login', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto(URLS.adminLogin);
    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/customadmin/dashboard/');
  });

  test('[SEC-05] Teacher cannot access Admin Dashboard', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/customadmin/dashboard/');
    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/customadmin/dashboard/');
  });

  test('[SEC-06] Teacher cannot access Admin Students', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto(URLS.adminStudents);
    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/customadmin/students/');
  });

  test('[SEC-07] Teacher cannot access Admin Analytics', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto(URLS.adminAnalytics);
    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/admin/analytics/');
  });

  test('[SEC-08] Unauthenticated user cannot access Dashboard', async ({ page }) => {
    await page.goto(URLS.dashboard);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[SEC-09] Unauthenticated user cannot access Teacher Dashboard', async ({ page }) => {
    await page.goto(URLS.teacherDashboard);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[SEC-10] Unauthenticated user cannot access Admin Dashboard', async ({ page }) => {
    await page.goto('/customadmin/dashboard/');
    await page.waitForTimeout(2000);
    const url = page.url();
    expect(url).not.toContain('/customadmin/dashboard/');
  });

  test('[SEC-11] Unauthenticated user cannot access Chat', async ({ page }) => {
    await page.goto(URLS.chatList);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[SEC-12] Unauthenticated user cannot access Notifications', async ({ page }) => {
    await page.goto(URLS.notifications);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[SEC-13] Unauthenticated user cannot access Profile', async ({ page }) => {
    await page.goto(URLS.profile);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[SEC-14] Unauthenticated user cannot access Analytics', async ({ page }) => {
    await page.goto(URLS.teacherAnalytics);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[SEC-15] Health endpoint is public', async ({ page }) => {
    await page.goto('/health/');
    const bodyText = await page.locator('body').textContent();
    expect(bodyText).toBeTruthy();
  });
});
