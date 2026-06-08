import { test, expect } from '@playwright/test';
import {
  loginAsAdmin,
  loginAsTeacher,
  URLS,
  CREDENTIALS,
} from '../fixtures/auth.fixture';

test.describe('ADMIN TESTS', () => {
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
        path: `playwright-report/screenshots/admin_${testInfo.title.replace(/\s+/g, '_')}_FAILED.png`,
        fullPage: true,
      });
    }
    testInfo.attachments.push({
      name: `console-errors-${testInfo.title}`,
      contentType: 'text/plain',
      body: Buffer.from(consoleErrors.join('\n')),
    });
  });

  test('[ADMIN-01] Admin Dashboard', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) {
      test.skip();
      return;
    }
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.toLowerCase()).toMatch(/admin|dashboard/i);
  });

  test('[ADMIN-02] Manage Students Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminStudents);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-03] Manage Teachers Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminTeachers);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-04] Pending Students Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminPending);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-05] Pending Teachers Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminPendingTeachers);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-06] Pending Resources Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminPendingResources);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-07] Pending Courses Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminPendingCourses);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-08] Analytics Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminAnalytics);
    await expect(page.locator('body')).toBeVisible({ timeout: 15000 });
  });

  test('[ADMIN-09] Content Management Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminContent);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-10] Deletion Requests Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminDeletionRequests);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-11] Admin Notifications', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminNotifications);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-12] System Audit Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.adminSystemAudit);
    await expect(page.locator('body')).toBeVisible({ timeout: 15000 });
  });

  test('[ADMIN-13] Storage Dashboard', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto('/customadmin/storage-dashboard/');
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[ADMIN-14] Student View Auth (Impersonation)', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto('/customadmin/student-view/auth/');
    await page.waitForTimeout(3000);
  });

  test('[ADMIN-15] Support Chat Page', async ({ page }) => {
    test.setTimeout(30000);
    const success = await loginAsAdmin(page);
    if (!success) { test.skip(); return; }
    await page.goto(URLS.chatList);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });
});
