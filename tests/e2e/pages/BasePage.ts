import { Page, expect } from '@playwright/test';

export class BasePage {
  constructor(protected page: Page) {}

  async goto(path: string) {
    await this.page.goto(path);
    await this.page.waitForLoadState('networkidle');
  }

  async verifyToastMessage(message: string) {
    // Assuming messages are in a standard Django message container or alert
    await expect(this.page.locator('text=' + message)).toBeVisible();
  }
}
