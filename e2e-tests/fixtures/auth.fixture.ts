import { Page, expect } from '@playwright/test';

export const CREDENTIALS = {
  student: { username: 'teststudent', password: 'Test@123' },
  teacher: { username: 'testteachernew', password: 'Test@123' },
  admin: { username: 'hashim', password: 'Test@123' },
};

export const URLS = {
  home: '/',
  login: '/login/',
  teacherLogin: '/teacher/login/',
  adminLogin: '/customadmin/portal-secure-access/',
  signup: '/signup/',
  teacherSignup: '/teacher/signup/',
  forgotPassword: '/forgot-password/',
  verifyOtp: '/verify-otp/',
  resetPassword: '/reset-password/',
  recoverUsername: '/recover-username/',
  dashboard: '/dashboard/',
  teacherDashboard: '/teacher/dashboard/',
  adminDashboard: '/customadmin/dashboard/',
  teacherCourses: '/teacher/courses/',
  teacherAnalytics: '/teacher/analytics/',
  studentExplore: '/student/explore/',
  profile: '/profile/',
  profileEdit: '/profile/edit/',
  chatList: '/chat/list/',
  notifications: '/notifications/',
  adminStudents: '/customadmin/students/',
  adminTeachers: '/customadmin/teachers/',
  adminPending: '/customadmin/pending/',
  adminPendingTeachers: '/customadmin/pending/teachers/',
  adminPendingResources: '/customadmin/pending/resources/',
  adminPendingCourses: '/customadmin/pending/courses/',
  adminAnalytics: '/customadmin/analytics/',
  adminContent: '/customadmin/content/',
  adminDeletionRequests: '/customadmin/deletion-requests/',
  adminNotifications: '/customadmin/notifications/',
  adminSystemAudit: '/customadmin/system-audit/',
};

export async function loginAsStudent(page: Page) {
  await page.goto(URLS.login);
  await page.waitForSelector('#loginForm', { timeout: 10000 });
  await page.fill('#username', CREDENTIALS.student.username);
  await page.fill('#password', CREDENTIALS.student.password);
  await page.click('#loginBtn');
  await page.waitForURL('**/dashboard/', { timeout: 15000 });
}

export async function loginAsTeacher(page: Page) {
  await page.goto(URLS.teacherLogin);
  await page.waitForSelector('#loginForm', { timeout: 10000 });
  await page.fill('#username', CREDENTIALS.teacher.username);
  await page.fill('#password', CREDENTIALS.teacher.password);
  await page.click('#loginBtn');
  await page.waitForURL('**/teacher/dashboard/', { timeout: 15000 });
}

export async function loginAsAdmin(page: Page) {
  await page.goto(URLS.adminLogin);
  await page.waitForSelector('#loginForm', { timeout: 10000 });
  await page.fill('#username', CREDENTIALS.admin.username);
  await page.fill('#password', CREDENTIALS.admin.password);
  await page.click('#loginBtn');

  await page.waitForTimeout(2000);

  // Check if TOTP 2FA step is shown
  const otpField = page.locator('#otp_code');
  if (await otpField.isVisible({ timeout: 3000 }).catch(() => false)) {
    console.log('TOTP 2FA required for admin login — cannot proceed without valid OTP');
    return false;
  }

  await page.waitForURL('**/customadmin/dashboard/', { timeout: 15000 });
  return true;
}

export async function logout(page: Page) {
  await page.goto('/logout/');
  await page.waitForURL('**/login/', { timeout: 10000 });
}

export async function captureState(page: Page, testName: string) {
  const screenshotPath = `screenshots/${testName.replace(/\s+/g, '_')}.png`;
  await page.screenshot({ path: screenshotPath, fullPage: true });
  return screenshotPath;
}

export function getConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  return errors;
}

export async function checkNoCriticalErrors(page: Page): Promise<boolean> {
  const logs: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      logs.push(msg.text());
    }
  });
  await page.waitForTimeout(500);
  const criticalErrors = logs.filter(
    (l) => l.includes('500') || l.includes('Internal Server Error') || l.includes('Failed to load')
  );
  return criticalErrors.length === 0;
}
