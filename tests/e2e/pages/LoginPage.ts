import { Page } from '@playwright/test';
import { BasePage } from './BasePage';

export class LoginPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async login(username: string, password: string) {
    await this.goto('/login/');
    await this.page.fill('#username', username);
    await this.page.fill('#password', password);
    await this.page.click('#loginBtn');
  }

  async adminLogin(username: string, password: string) {
    // Admin login is on a hidden URL
    await this.goto('/customadmin/portal-secure-access/');
    await this.page.fill('input[name="username"]', username);
    await this.page.fill('input[name="password"]', password);
    await this.page.click('button[type="submit"]');
  }

  async logout() {
    await this.page.goto('/logout/');
  }
}
