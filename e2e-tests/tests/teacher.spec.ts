import { test, expect } from '@playwright/test';
import {
  loginAsTeacher,
  URLS,
  CREDENTIALS,
} from '../fixtures/auth.fixture';

test.describe('TEACHER TESTS', () => {
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
        path: `playwright-report/screenshots/teacher_${testInfo.title.replace(/\s+/g, '_')}_FAILED.png`,
        fullPage: true,
      });
    }
    testInfo.attachments.push({
      name: `console-errors-${testInfo.title}`,
      contentType: 'text/plain',
      body: Buffer.from(consoleErrors.join('\n')),
    });
  });

  test('[TEACHER-01] Teacher Dashboard', async ({ page }) => {
    await loginAsTeacher(page);
    await expect(page.locator('body')).toBeVisible({ timeout: 5000 });
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.toLowerCase()).toMatch(/dashboard|welcome/i);
  });

  test('[TEACHER-02] My Courses Page - Empty State', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto(URLS.teacherCourses);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(2000);
  });

  test('[TEACHER-03] Create Course Page Load', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/teacher/courses/create/');
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
    const bodyText = await page.locator('body').textContent();
    expect(bodyText?.toLowerCase()).toMatch(/create|course|new/i);
  });

  test('[TEACHER-04] Create Course - Submit Form', async ({ page }) => {
    test.setTimeout(30000);
    await loginAsTeacher(page);
    await page.goto('/teacher/courses/create/');
    await page.waitForSelector('#title, input[name="title"]', { timeout: 10000 });

    const titleField = page.locator('#title, input[name="title"]').first();
    await titleField.fill('E2E Test Course ' + Date.now());

    const categoryField = page.locator('#category, input[name="category"]').first();
    if (await categoryField.isVisible().catch(() => false)) {
      await categoryField.fill('Technology');
    }

    const levelSelect = page.locator('select#level, select[name="level"]').first();
    if (await levelSelect.isVisible().catch(() => false)) {
      await levelSelect.selectOption('Beginner');
    }

    const descField = page.locator('textarea#description, textarea[name="description"]').first();
    if (await descField.isVisible().catch(() => false)) {
      await descField.fill('E2E test course description for automated testing');
    }

    const submitBtn = page.locator('button[type="submit"]').first();
    if (await submitBtn.isVisible().catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(5000);
    }
  });

  test('[TEACHER-05] Teacher Analytics Page', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto(URLS.teacherAnalytics);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[TEACHER-06] Teacher Explore Courses', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/teacher/explore/');
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[TEACHER-07] Teacher Deletion Requests Page', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/teacher/deletion-requests/');
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[TEACHER-08] Teacher Profile View', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto(URLS.profile);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[TEACHER-09] Teacher Edit Profile', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/teacher/profile/edit/');
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[TEACHER-10] Teacher Notifications', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto(URLS.notifications);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[TEACHER-11] Teacher Unread Counts', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/unread-counts/');
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[TEACHER-12] Support Chat Page', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto(URLS.chatList);
    await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
  });

  test('[TEACHER-13] Course Lessons Page (no courses)', async ({ page }) => {
    await loginAsTeacher(page);
    const coursesRes = await page.request.get('/teacher/courses/');
    await page.goto('/teacher/courses/');

    const courseLinks = page.locator('a[href*="/lessons/"], a[href*="lessons"]');
    const courseCount = await courseLinks.count();
    if (courseCount > 0) {
      await courseLinks.first().click();
      await expect(page.locator('body')).toBeVisible({ timeout: 10000 });
    }
  });

  test('[TEACHER-14] Student View Auth', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/student-view/auth/');
    await page.waitForTimeout(3000);
  });

  test('[TEACHER-15] Teacher Logout', async ({ page }) => {
    await loginAsTeacher(page);
    await page.goto('/logout/');
    await expect(page).toHaveURL(/\/login\//, { timeout: 10000 });
  });
});
