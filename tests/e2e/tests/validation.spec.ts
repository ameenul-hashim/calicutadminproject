import { test, expect } from '../helpers/test-utils';
import path from 'path';

test.describe('Form Validations', () => {
  test('Signup Form: Required Fields', async ({ page }) => {
    await page.goto('/signup/');
    // Fill nothing, click signup
    await page.click('#signup-btn');
    
    // Check for validation error cards
    const errorCard = page.locator('.validation-card.error').first();
    await expect(errorCard).toBeVisible();
    await expect(errorCard).toContainText('required');
  });

  test('Signup Form: Invalid Email', async ({ page }) => {
    await page.goto('/signup/');
    await page.fill('#email', 'not-an-email');
    await page.click('#signup-btn');
    
    const emailError = page.locator('.validation-card.error', { hasText: /email/i });
    await expect(emailError).toBeVisible();
    await expect(emailError).toContainText(/format|invalid/i);
  });

  test('Login Form: Missing Credentials', async ({ page }) => {
    await page.goto('/login/');
    await page.click('#loginBtn');
    
    // Check for validation cards in login form
    const errorCard = page.locator('.validation-card.error').first();
    await expect(errorCard).toBeVisible();
    await expect(errorCard).toContainText('required');
  });

  test('File Upload: Invalid File Type', async ({ page }) => {
    await page.goto('/signup/');
    
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.click('#upload-label');
    const fileChooser = await fileChooserPromise;
    // Upload a text file instead of PDF
    await fileChooser.setFiles(path.join(process.cwd(), 'package.json'));
    
    // Check for Toast error or Validation Card
    // According to signup.html, it triggers Toast.error immediately
    await expect(page.locator('text=only PDF files are allowed')).toBeVisible();
  });
});
