import { test, expect, Page } from '@playwright/test';
import {
  loginAsStudent,
  loginAsTeacher,
  loginAsAdmin,
  logout,
  CREDENTIALS,
  URLS,
  captureState,
} from '../fixtures/auth.fixture';

test.describe('AUTH TESTS', () => {
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
        path: `playwright-report/screenshots/${testInfo.title.replace(/\s+/g, '_')}_FAILED.png`,
        fullPage: true,
      });
    }
    testInfo.attachments.push({
      name: 'console-errors',
      contentType: 'text/plain',
      body: Buffer.from(consoleErrors.join('\n')),
    });
  });

  test('[AUTH-01] Student Login - Valid Credentials', async ({ page }) => {
    await page.goto(URLS.login);
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10000 });
    await page.fill('#username', CREDENTIALS.student.username);
    await page.fill('#password', CREDENTIALS.student.password);
    await page.click('#loginBtn');
    await expect(page).toHaveURL(/\/dashboard\//, { timeout: 15000 });
    await expect(page.locator('body')).toContainText(/welcome|dashboard/i);
  });

  test('[AUTH-02] Student Login - Invalid Password', async ({ page }) => {
    await page.goto(URLS.login);
    await page.fill('#username', CREDENTIALS.student.username);
    await page.fill('#password', 'WrongPassword123!');
    await page.click('#loginBtn');
    await page.waitForTimeout(2000);
    const body = await page.locator('body').textContent();
    expect(body?.toLowerCase()).toMatch(/invalid|incorrect|error|wrong/i);
  });

  test('[AUTH-03] Student Login - Empty Fields', async ({ page }) => {
    await page.goto(URLS.login);
    await page.click('#loginBtn');
    await page.waitForTimeout(1000);
    const url = page.url();
    expect(url).not.toContain('/dashboard/');
  });

  test('[AUTH-04] Teacher Login - Valid Credentials', async ({ page }) => {
    await page.goto(URLS.teacherLogin);
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10000 });
    await page.fill('#username', CREDENTIALS.teacher.username);
    await page.fill('#password', CREDENTIALS.teacher.password);
    await page.click('#loginBtn');
    await expect(page).toHaveURL(/\/teacher\/dashboard\//, { timeout: 15000 });
    await expect(page.locator('body')).toContainText(/dashboard|welcome/i);
  });

  test('[AUTH-05] Teacher Login - Invalid Password', async ({ page }) => {
    await page.goto(URLS.teacherLogin);
    await page.fill('#username', CREDENTIALS.teacher.username);
    await page.fill('#password', 'WrongPassword123!');
    await page.click('#loginBtn');
    await page.waitForTimeout(2000);
    const body = await page.locator('body').textContent();
    expect(body?.toLowerCase()).toMatch(/invalid|incorrect|error|wrong/i);
  });

  test('[AUTH-06] Admin Login Page Access', async ({ page }) => {
    await page.goto(URLS.adminLogin);
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('#username')).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
  });

  test('[AUTH-07] Admin Login - Valid Credentials (SKIP if 2FA)', async ({ page }) => {
    test.setTimeout(30000);
    await page.goto(URLS.adminLogin);
    await expect(page.locator('#loginForm')).toBeVisible({ timeout: 10000 });
    await page.fill('#username', CREDENTIALS.admin.username);
    await page.fill('#password', CREDENTIALS.admin.password);
    await page.click('#loginBtn');
    await page.waitForTimeout(3000);
    const otpField = page.locator('#otp_code');
    if (await otpField.isVisible({ timeout: 3000 }).catch(() => false)) {
      test.skip();
      return;
    }
    await expect(page).toHaveURL(/\/customadmin\/dashboard\//, { timeout: 15000 });
  });

  test('[AUTH-08] Logout - Student', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/logout/');
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
    await page.goto(URLS.dashboard);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[AUTH-09] Logout - Teacher', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/logout/');
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
    await page.goto(URLS.teacherDashboard);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[AUTH-10] Forgot Password Page Load', async ({ page }) => {
    await page.goto(URLS.forgotPassword);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
    const body = await page.locator('body').textContent();
    expect(body?.toLowerCase()).toMatch(/forgot|recover|reset|password/i);
  });

  test('[AUTH-11] Forgot Password - Submit Form', async ({ page }) => {
    await page.goto(URLS.forgotPassword);
    const usernameField = page.locator('#username');
    const emailField = page.locator('#email');
    if (await usernameField.isVisible({ timeout: 3000 }).catch(() => false)) {
      await usernameField.fill(CREDENTIALS.student.username);
    }
    if (await emailField.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emailField.fill('teststudent123@gmail.com');
    }
    const submitBtn = page.locator('button[type="submit"]');
    if (await submitBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(3000);
    }
  });

  test('[AUTH-12] Recover Username Page Load', async ({ page }) => {
    await page.goto(URLS.recoverUsername);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[AUTH-13] Unauthorized Access - Redirect to Login', async ({ page }) => {
    await page.goto(URLS.dashboard);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[AUTH-14] Teacher Unauthorized Access - Redirect to Login', async ({ page }) => {
    await page.goto(URLS.teacherDashboard);
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });

  test('[AUTH-15] Session Persistence - Student Dashboard After Login', async ({ page }) => {
    await loginAsStudent(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.toLowerCase()).toContain('teststudent');
  });
});
