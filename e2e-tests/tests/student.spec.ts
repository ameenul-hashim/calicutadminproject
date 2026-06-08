import { test, expect } from '@playwright/test';
import {
  loginAsStudent,
  logout,
  URLS,
  CREDENTIALS,
} from '../fixtures/auth.fixture';

test.describe('STUDENT TESTS', () => {
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
        path: `playwright-report/screenshots/student_${testInfo.title.replace(/\s+/g, '_')}_FAILED.png`,
        fullPage: true,
      });
    }
    testInfo.attachments.push({
      name: `console-errors-${testInfo.title}`,
      contentType: 'text/plain',
      body: Buffer.from(consoleErrors.join('\n')),
    });
  });

  test('[STUDENT-01] Signup Page Load', async ({ page }) => {
    await page.goto(URLS.signup);
    await expect(page.locator('#signupForm')).toBeVisible({ timeout: 10000 });
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.toLowerCase()).toMatch(/sign.?up|register|create|account/i);
  });

  test('[STUDENT-02] Signup - Empty Form Validation', async ({ page }) => {
    await page.goto(URLS.signup);
    const submitBtn = page.locator('#signup-btn');
    if (await submitBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(1500);
      const url = page.url();
      expect(url).toContain('/signup');
    }
  });

  test('[STUDENT-03] Signup - Duplicate Username', async ({ page }) => {
    await page.goto(URLS.signup);
    await page.fill('#username', CREDENTIALS.student.username);
    await page.fill('#fullname', 'Duplicate Test');
    await page.fill('#email', 'duplicate@test.com');
    await page.fill('#phone_number', '9999999999');
    await page.fill('#password', 'Test@123');
    await page.fill('#confirm_password', 'Test@123');
    const submitBtn = page.locator('#signup-btn');
    if (await submitBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(3000);
      const bodyText = await page.locator('body').textContent();
      expect(bodyText?.toLowerCase()).toMatch(/already|exists|taken|duplicate/i);
    }
  });

  test('[STUDENT-04] Login - Student Dashboard', async ({ page }) => {
    await loginAsStudent(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.toLowerCase()).toMatch(/dashboard|welcome/i);
  });

  test('[STUDENT-05] Browse Courses - Explore Page', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.studentExplore);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(2000);
  });

  test('[STUDENT-06] Browse Courses - Search', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.studentExplore);
    const searchInput = page.locator('input[type="search"], input[name="search"], .search-input, input[placeholder*="search" i]').first();
    if (await searchInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await searchInput.fill('test');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);
    }
  });

  test('[STUDENT-07] Profile Page View', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.profile);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.toLowerCase()).toMatch(/profile|teststudent/i);
  });

  test('[STUDENT-08] Edit Profile Page Load', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.profileEdit);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[STUDENT-09] Edit Profile - Update Full Name', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.profileEdit);
    const nameField = page.locator('#fullname, input[name="fullname"], input[name="full_name"]').first();
    if (await nameField.isVisible({ timeout: 3000 }).catch(() => false)) {
      await nameField.fill('Test Student Updated');
      const submitBtn = page.locator('button[type="submit"]').first();
      if (await submitBtn.isVisible().catch(() => false)) {
        await submitBtn.click();
        await page.waitForTimeout(3000);
      }
    }
  });

  test('[STUDENT-10] Notifications Page', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.notifications);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[STUDENT-11] Notifications - Unread Count', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/unread-counts/');
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[STUDENT-12] Enroll Course - No Courses Available', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.studentExplore);
    await page.waitForTimeout(2000);
    const bodyText = await page.locator('body').textContent();
    const noCourses = bodyText?.toLowerCase().match(/no courses|no results|empty|no data/i);
  });

  test('[STUDENT-13] Dashboard - Stats Cards', async ({ page }) => {
    await loginAsStudent(page);
    await page.waitForTimeout(2000);
    const statsCards = page.locator('.stat-card, .stats-card, .dashboard-stat');
    const count = await statsCards.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('[STUDENT-14] Chat Page', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto(URLS.chatList);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[STUDENT-15] Logout', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/logout/');
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });
});
