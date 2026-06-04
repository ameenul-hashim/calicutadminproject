import { test, expect } from '../helpers/test-utils';
import path from 'path';

test('Debug Signup', async ({ page }) => {
  const timestamp = Date.now();
  await page.goto('/signup/');
  await page.fill('#username', `user_${timestamp}`);
  await page.fill('#fullname', `User ${timestamp}`);
  await page.fill('#email', `user_${timestamp}@example.com`);
  await page.fill('#phone_number', '9123456789');
  
  const fileChooserPromise = page.waitForEvent('filechooser');
  await page.click('#upload-label');
  const fileChooser = await fileChooserPromise;
  await fileChooser.setFiles(path.join(process.cwd(), 'test_resource.pdf'));

  await page.fill('#password', 'StrongPass123!');
  await page.fill('#confirm_password', 'StrongPass123!');
  
  console.log('Submitting signup...');
  await page.click('#signup-btn');
  
  // Wait for 10 seconds to see what happens
  await page.waitForTimeout(10000);
  
  const url = page.url();
  console.log('Final URL:', url);
  
  await page.screenshot({ path: 'signup_debug.png', fullPage: true });
  
  const errorCards = await page.locator('.validation-card.error').allTextContents();
  console.log('Error cards:', errorCards);
  
  const toastMessage = await page.locator('.toast').allTextContents(); // Guessing toast class
  console.log('Toast messages:', toastMessage);
});
