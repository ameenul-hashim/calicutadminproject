import { test, expect } from '@playwright/test';
import {
  loginAsStudent,
  loginAsTeacher,
  URLS,
} from '../fixtures/auth.fixture';

test.describe('RESPONSIVE TESTS', () => {
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
        path: `playwright-report/screenshots/responsive_${testInfo.title.replace(/\s+/g, '_')}_FAILED.png`,
        fullPage: true,
      });
    }
  });

  test('[RESP-01] Desktop viewport - Student Login', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(URLS.login);
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10000 });
    const formWidth = await page.locator('#loginForm').evaluate(el => el.getBoundingClientRect().width);
    expect(formWidth).toBeLessThan(500);
  });

  test('[RESP-02] Desktop viewport - Teacher Login', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(URLS.teacherLogin);
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10000 });
  });

  test('[RESP-03] Desktop viewport - Student Dashboard', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await loginAsStudent(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.toLowerCase()).toMatch(/dashboard|welcome/i);
  });

  test('[RESP-04] Desktop viewport - Teacher Dashboard', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await loginAsTeacher(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
  });

  test('[RESP-05] Tablet viewport - Student Login', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto(URLS.login);
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10000 });
  });

  test('[RESP-06] Tablet viewport - Signup Page', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto(URLS.signup);
    await expect(page.locator('#signupForm')).toBeVisible({ timeout: 10000 });
  });

  test('[RESP-07] Tablet viewport - Student Dashboard', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await loginAsStudent(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
  });

  test('[RESP-08] Tablet viewport - Teacher Dashboard', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await loginAsTeacher(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
  });

  test('[RESP-09] Mobile viewport - Student Login', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto(URLS.login);
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10000 });
  });

  test('[RESP-10] Mobile viewport - Signup Page', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto(URLS.signup);
    await expect(page.locator('#signupForm')).toBeVisible({ timeout: 10000 });
  });

  test('[RESP-11] Mobile viewport - Student Dashboard', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await loginAsStudent(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
  });

  test('[RESP-12] Mobile viewport - Teacher Dashboard', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await loginAsTeacher(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
  });

  test('[RESP-13] Mobile viewport - Student Explore', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await loginAsStudent(page);
    await page.goto(URLS.studentExplore);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[RESP-14] Mobile viewport - Profile Page', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await loginAsStudent(page);
    await page.goto(URLS.profile);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[RESP-15] Mobile viewport - Notifications', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await loginAsStudent(page);
    await page.goto(URLS.notifications);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });
});
