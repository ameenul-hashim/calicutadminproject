import { test, expect } from '../helpers/test-utils';

test.describe('Security & Role Isolation', () => {

  test('Student cannot access Admin Dashboard', async ({ page }) => {
    await page.goto('/customadmin/dashboard/');
    // Instead of checking the full URL, we check that we are NOT on the dashboard
    // and that the current URL contains the security login portal path
    await expect(page).not.toHaveURL(/\/customadmin\/dashboard\/$/);
    await expect(page.url()).toContain('portal-secure-access');
  });

  test('Student cannot access Teacher Dashboard', async ({ page }) => {
    await page.goto('/teacher/dashboard/');
    await expect(page).not.toHaveURL(/\/teacher\/dashboard\/$/);
    await expect(page.url()).toContain('login');
  });

  test('Teacher cannot access Admin Dashboard', async ({ page }) => {
    await page.goto('/customadmin/dashboard/');
    await expect(page).not.toHaveURL(/\/customadmin\/dashboard\/$/);
    await expect(page.url()).toContain('portal-secure-access');
  });

  test('Permission Bypass Check: Direct Course Edit', async ({ page }) => {
    await page.goto('/teacher/courses/123/edit/');
    await expect(page).not.toHaveURL(/\/teacher\/courses\/123\/edit\/$/);
    await expect(page.url()).toContain('login');
  });
});
