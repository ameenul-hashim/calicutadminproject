import { test, expect } from '@playwright/test';
import { LoginPage } from '../pages/LoginPage';
import path from 'path';

test.describe('Student Workflow', () => {
  const timestamp = Date.now();
  const studentUser = {
    username: `student_${timestamp}`,
    fullname: `Student ${timestamp}`,
    email: `student_${timestamp}@example.com`,
    phone: '9876543210',
    password: 'Password123!'
  };

  test('Signup Workflow', async ({ page }) => {
    await page.goto('/signup/');
    
    // Fill signup form
    await page.fill('#username', studentUser.username);
    await page.fill('#fullname', studentUser.fullname);
    await page.fill('#email', studentUser.email);
    await page.fill('#phone_number', studentUser.phone);
    
    // Upload proof document (must be PDF < 200KB for non-mobile simulation)
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.click('#upload-label');
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(path.join(process.cwd(), 'test_resource.pdf'));
    
    await page.fill('#password', studentUser.password);
    await page.fill('#confirm_password', studentUser.password);
    
    // Submit
    await page.click('#signup-btn');
    
    // Check for success message or redirect to login
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('text=success')).toBeVisible();
  });

  test('Login & Dashboard Access', async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.login(studentUser.username, studentUser.password);
    
    // Student should be directed to dashboard
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator('text=Welcome')).toBeVisible();
    
    // Check navigation
    await page.click('text=Explore Courses');
    await expect(page).toHaveURL(/.*explore/);
  });
});
