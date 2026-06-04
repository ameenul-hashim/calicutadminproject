const { test, expect } = require('@playwright/test');
const path = require('path');
const {
  BASE_URL, timestamp, createTeacherCredentials,
  navigateAndWait, waitForSelectorSafe, takeScreenshot,
  logPageState, collectConsoleErrors, tryClick, tryFill,
  checkElementExists, getTestPdfPath,
  ADMIN_CREDENTIALS, ADMIN_PORTAL,
} = require('./helpers');

const bugs = [];
let teacher = null;
let courseUid = null;
let lessonUid = null;
let resourceUid = null;

function setupConsoleCapture(page) {
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));
  page.on('requestfailed', req => errors.push(`NET: ${req.url()} ${req.failure()?.errorText}`));
  return errors;
}

async function tryNavigate(page, url) {
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    return true;
  } catch (e) {
    console.log(`[NAV] Timeout/error for ${url}: ${e.message}`);
    return false;
  }
}

test.describe('Teacher Flow - Full LMS Audit', () => {

  // ===================================================================
  // TEACHER-01: TEACHER SIGNUP
  // ===================================================================
  test('TEACHER-01: Teacher Signup - Create Account', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    const creds = createTeacherCredentials();
    teacher = creds;

    try {
      console.log(`[TEACHER-01] Creating teacher: ${creds.username} / ${creds.email}`);

      const navOk = await navigateAndWait(page, '/teacher/signup/');
      if (!navOk) throw new Error('Failed to navigate to /teacher/signup/');
      await logPageState(page, 'TEACHER-01-signup-page');

      await tryFill(page, '#fullname', creds.fullName);
      await tryFill(page, '#email', creds.email);
      await tryFill(page, '#username', creds.username);
      await tryFill(page, '#password', creds.password);
      await tryFill(page, '#confirm_password', creds.password);
      await tryFill(page, '#phone_number', creds.phone);

      const pdfPath = getTestPdfPath();
      console.log(`[TEACHER-01] Using PDF: ${pdfPath}`);

      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      await tryClick(page, '#upload-label');
      const fileChooser = await fileChooserPromise;
      if (fileChooser) {
        await fileChooser.setFiles([pdfPath]);
        console.log('[TEACHER-01] PDF selected via file chooser');
      } else {
        const inputSelector = '#proof_file, input[type="file"]';
        await page.setInputFiles(inputSelector, pdfPath).catch(e => {
          console.log(`[TEACHER-01] Direct file input failed: ${e.message}`);
        });
      }

      await page.waitForTimeout(500);
      const submitBtn = page.locator('#signup-btn, button[type="submit"]').first();
      await submitBtn.click();
      console.log('[TEACHER-01] Signup form submitted');

      await page.waitForTimeout(3000);

      const currentUrl = page.url();
      console.log(`[TEACHER-01] URL after signup: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[TEACHER-01] SUCCESS: Redirected to login page');
        const successMsg = await page.locator('.alert-success, .toast-message, .messages .success, [class*="success"]').first().textContent().catch(() => 'not found');
        console.log(`[TEACHER-01] Success message: ${successMsg}`);
      } else if (currentUrl.includes('/signup/')) {
        const errors = await page.locator('.validation-card.error, .alert-error, .alert-danger, .toast-message, [class*="error"]').allTextContents().catch(() => []);
        console.log(`[TEACHER-01] Still on signup. Errors: ${JSON.stringify(errors)}`);
      } else {
        console.log(`[TEACHER-01] Unexpected redirect to: ${currentUrl}`);
      }

      await takeScreenshot(page, 'TEACHER-01-signup-result');
      await logPageState(page, 'TEACHER-01-final');

    } catch (e) {
      console.error(`[TEACHER-01] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-01: Teacher Signup',
        error: e.message, reproduction: 'Navigate to /teacher/signup/, fill all fields, upload PDF, submit',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-01-fail');
    }
  });

  // ===================================================================
  // TEACHER-02: SIGNUP VALIDATION
  // ===================================================================
  test('TEACHER-02a: Signup Validation - Empty Form', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-02a] Testing empty form submission');
      await navigateAndWait(page, '/teacher/signup/');
      await logPageState(page, 'TEACHER-02a-page');

      const submitBtn = page.locator('#signup-btn, button[type="submit"]').first();
      await submitBtn.click();
      await page.waitForTimeout(1500);

    // Wait for either JS validation cards or server-side toast messages
    await page.waitForTimeout(1000);
    const validationCards = await page.locator('.validation-card.error').count();
    const toastMessages = await page.locator('.toast-message').count();
    const otherErrorElements = await page.locator('.alert, .error, [class*="error"], [class*="alert"]').count();
    console.log(`[TEACHER-02a] Validation cards: ${validationCards}, Toast messages: ${toastMessages}, Other errors: ${otherErrorElements}`);

    const allErrors = [
      ...(await page.locator('.validation-card').allTextContents().catch(() => [])),
      ...(await page.locator('.toast-message').allTextContents().catch(() => [])),
    ];
    console.log(`[TEACHER-02a] All error texts: ${JSON.stringify(allErrors)}`);

    if (validationCards === 0 && toastMessages === 0 && otherErrorElements === 0) {
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-02a: Empty Form Validation',
        error: 'No validation error appeared for empty form submission (no JS validation cards or server-side toast messages)',
        reproduction: 'Navigate to /teacher/signup/, click submit without filling any fields',
        console: [...consoleErrors],
      });
    }

      await takeScreenshot(page, 'TEACHER-02a-empty-form');
      await logPageState(page, 'TEACHER-02a-final');
    } catch (e) {
      console.error(`[TEACHER-02a] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-02a: Empty Form Validation',
        error: e.message, reproduction: 'Submit empty teacher signup form',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-02a-fail');
    }
  });

  test('TEACHER-02b: Signup Validation - Invalid Email', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-02b] Testing invalid email validation');
      await navigateAndWait(page, '/teacher/signup/');
      await logPageState(page, 'TEACHER-02b-page');

      await tryFill(page, '#fullname', 'Invalid Email Teacher');
      await tryFill(page, '#email', 'not-an-email');
      await tryFill(page, '#username', `invalid_email_tchr_${timestamp()}`);
      await tryFill(page, '#password', 'TestPass123!');
      await tryFill(page, '#confirm_password', 'TestPass123!');
      await tryFill(page, '#phone_number', '9876543210');

      const pdfPath = getTestPdfPath();
      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      await tryClick(page, '#upload-label');
      const fileChooser = await fileChooserPromise;
      if (fileChooser) {
        await fileChooser.setFiles([pdfPath]);
      } else {
        await page.setInputFiles('#proof_file, input[type="file"]', pdfPath).catch(() => {});
      }

      const submitBtn = page.locator('#signup-btn, button[type="submit"]').first();
      await submitBtn.click();
      await page.waitForTimeout(1500);

    // Wait for either JS validation cards or server-side toast messages
    await page.waitForTimeout(1000);
    const allErrors = [
      ...(await page.locator('.validation-card').allTextContents().catch(() => [])),
      ...(await page.locator('.toast-message').allTextContents().catch(() => [])),
    ];
    console.log(`[TEACHER-02b] All errors: ${JSON.stringify(allErrors)}`);

    const hasEmailError = allErrors.some(t =>
      t.toLowerCase().includes('email') || t.toLowerCase().includes('invalid')
    );

    if (!hasEmailError) {
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-02b: Invalid Email Validation',
        error: 'No email validation error for "not-an-email"',
        reproduction: 'Fill teacher signup with invalid email, submit',
        console: [...consoleErrors],
      });
    }

      await takeScreenshot(page, 'TEACHER-02b-invalid-email');
      await logPageState(page, 'TEACHER-02b-final');
    } catch (e) {
      console.error(`[TEACHER-02b] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-02b: Invalid Email',
        error: e.message, reproduction: 'Submit teacher signup with bad email',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-02b-fail');
    }
  });

  test('TEACHER-02c: Signup Validation - Duplicate Credentials', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!teacher) {
        console.log('[TEACHER-02c] No teacher credentials from TEACHER-01, skipping duplicate test');
        return;
      }
      console.log(`[TEACHER-02c] Testing duplicate signup with: ${teacher.username}`);
      await navigateAndWait(page, '/teacher/signup/');
      await logPageState(page, 'TEACHER-02c-page');

      await tryFill(page, '#fullname', teacher.fullName);
      await tryFill(page, '#email', teacher.email);
      await tryFill(page, '#username', teacher.username);
      await tryFill(page, '#password', teacher.password);
      await tryFill(page, '#confirm_password', teacher.password);
      await tryFill(page, '#phone_number', teacher.phone);

      const pdfPath = getTestPdfPath();
      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      await tryClick(page, '#upload-label');
      const fileChooser = await fileChooserPromise;
      if (fileChooser) {
        await fileChooser.setFiles([pdfPath]);
      } else {
        await page.setInputFiles('#proof_file, input[type="file"]', pdfPath).catch(() => {});
      }

      const submitBtn = page.locator('#signup-btn, button[type="submit"]').first();
      await submitBtn.click();
      await page.waitForTimeout(3000);

      const currentUrl = page.url();
      console.log(`[TEACHER-02c] URL after submission: ${currentUrl}`);

    const allErrors = [
      ...(await page.locator('.validation-card').allTextContents().catch(() => [])),
      ...(await page.locator('.toast-message').allTextContents().catch(() => [])),
    ];
    const bodyText = allErrors.join(' ') + ' ' + (await page.locator('body').textContent().catch(() => ''));
    const hasDuplicateMsg = bodyText.toLowerCase().includes('username') ||
                            bodyText.toLowerCase().includes('already') ||
                            bodyText.toLowerCase().includes('exists') ||
                            bodyText.toLowerCase().includes('taken') ||
                            bodyText.toLowerCase().includes('duplicate') ||
                            bodyText.toLowerCase().includes('email');

    if (currentUrl.includes('/login/') && !currentUrl.includes('/teacher/login/')) {
      console.log('[TEACHER-02c] Redirected to login - duplicate was not blocked');
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-02c: Duplicate Signup',
        error: 'Duplicate teacher signup was not rejected (redirected to login)',
        reproduction: `Try creating teacher with existing username/email`,
        console: [...consoleErrors],
      });
    } else if (currentUrl.includes('/signup/') && !hasDuplicateMsg) {
      console.log('[TEACHER-02c] On signup page - no obvious duplicate message');
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-02c: Duplicate Signup',
        error: 'Duplicate credentials not clearly rejected with error message',
        reproduction: 'Submit teacher signup with existing credentials',
        console: [...consoleErrors],
      });
    } else if (currentUrl.includes('/teacher/login/')) {
      console.log('[TEACHER-02c] Redirected to teacher login - signup succeeded or server accepted');
    } else {
      console.log(`[TEACHER-02c] Current URL: ${currentUrl}`);
    }

      await takeScreenshot(page, 'TEACHER-02c-duplicate');
      await logPageState(page, 'TEACHER-02c-final');
    } catch (e) {
      console.error(`[TEACHER-02c] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-02c: Duplicate Signup',
        error: e.message, reproduction: 'Submit duplicate teacher signup',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-02c-fail');
    }
  });

  // ===================================================================
  // TEACHER-03: LOGIN PENDING
  // ===================================================================
  test('TEACHER-03a: Login as Pending Teacher', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!teacher) throw new Error('No teacher credentials from TEACHER-01');
      console.log(`[TEACHER-03a] Attempting login with pending teacher: ${teacher.username}`);

      await navigateAndWait(page, '/teacher/login/');
      await logState(page, 'TEACHER-03a-login-page');

      await tryFill(page, '#username', teacher.username);
      await tryFill(page, '#password', teacher.password);

      const loginBtn = page.locator('#loginBtn, button[type="submit"]').first();
      await loginBtn.click();
      await page.waitForTimeout(3000);

      const currentUrl = page.url();
      console.log(`[TEACHER-03a] URL after login: ${currentUrl}`);

      const bodyText = await page.locator('body').textContent().catch(() => '');
      const hasPendingMsg = bodyText.toLowerCase().includes('pending') ||
                            bodyText.toLowerCase().includes('approval') ||
                            bodyText.toLowerCase().includes('not approved') ||
                            bodyText.toLowerCase().includes('inactive') ||
                            bodyText.toLowerCase().includes('blocked') ||
                            bodyText.toLowerCase().includes('wait');

      console.log(`[TEACHER-03a] Pending message found: ${hasPendingMsg}`);

      if (currentUrl.includes('/dashboard/') || currentUrl.includes('/teacher/dashboard/')) {
        console.log('[TEACHER-03a] NOTE: Pending teacher was able to log in (may have been pre-approved)');
      } else if (!hasPendingMsg && (currentUrl.includes('/login/') || currentUrl.includes('/teacher/login/'))) {
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-03a: Pending Login',
          error: 'No pending-approval message for unapproved teacher login attempt',
          reproduction: `Login with unapproved teacher "${teacher.username}"`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-03a-pending-login');
      await logState(page, 'TEACHER-03a-final');
    } catch (e) {
      console.error(`[TEACHER-03a] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-03a: Pending Login',
        error: e.message, reproduction: 'Login as pending teacher',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-03a-fail');
    }
  });

  test('TEACHER-03b: Direct Dashboard Access as Pending Teacher', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-03b] Attempting direct /teacher/dashboard/ access');
      await navigateAndWait(page, '/teacher/dashboard/');
      await logState(page, 'TEACHER-03b-dashboard-access');

      const currentUrl = page.url();
      console.log(`[TEACHER-03b] Final URL: ${currentUrl}`);

      if (currentUrl.includes('/login/') || currentUrl.includes('/teacher/login/')) {
        console.log('[TEACHER-03b] SUCCESS: Redirected to login page');
      } else if (currentUrl.includes('/dashboard/')) {
        console.log('[TEACHER-03b] Dashboard loaded (teacher may be approved)');
      } else {
        console.log(`[TEACHER-03b] Unexpected location: ${currentUrl}`);
      }

      await takeScreenshot(page, 'TEACHER-03b-direct-dashboard');
      await logState(page, 'TEACHER-03b-final');
    } catch (e) {
      console.error(`[TEACHER-03b] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-03b: Direct Dashboard',
        error: e.message, reproduction: 'Navigate to /teacher/dashboard/ while logged out',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-03b-fail');
    }
  });

  // ===================================================================
  // TEACHER-04: ADMIN APPROVAL & POST-APPROVAL LOGIN
  // ===================================================================
  test('TEACHER-04: Admin Approval of Teacher', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!teacher) throw new Error('No teacher credentials');
      console.log('[TEACHER-04] Logging in as admin to approve teacher');

      await navigateAndWait(page, ADMIN_PORTAL);
      await logState(page, 'TEACHER-04-admin-login');

      await tryFill(page, '#username', ADMIN_CREDENTIALS.username);
      await tryFill(page, '#password', ADMIN_CREDENTIALS.password);
      const loginBtn = page.locator('#loginBtn, button[type="submit"]').first();
      await loginBtn.click();
      await page.waitForTimeout(3000);
      console.log(`[TEACHER-04] Admin login result URL: ${page.url()}`);

      await navigateAndWait(page, '/customadmin/pending/teachers/');
      await page.waitForTimeout(2000);
      await logState(page, 'TEACHER-04-pending-teachers');

      const bodyText = await page.locator('body').textContent().catch(() => '');
      console.log(`[TEACHER-04] Page contains teacher username "${teacher.username}": ${bodyText.includes(teacher.username)}`);

      const teacherLink = page.locator(`a:has-text("${teacher.username}"), td:has-text("${teacher.username}"), tr:has-text("${teacher.username}")`).first();
      if (await teacherLink.count() > 0) {
        console.log('[TEACHER-04] Found pending teacher, attempting to approve...');
        const approveBtn = page.locator(`a:has-text("Approve"), a:has-text("Accept"), button:has-text("Approve"), button:has-text("Accept"), .btn-approve, .btn-accept`).first();
        if (await approveBtn.count() > 0) {
          await approveBtn.click();
          await page.waitForTimeout(2000);
          console.log(`[TEACHER-04] URL after approve click: ${page.url()}`);
        } else {
          const userActionLinks = page.locator(`a[href*="accept"], a[href*="approve"]`).first();
          if (await userActionLinks.count() > 0) {
            await userActionLinks.click();
            await page.waitForTimeout(2000);
            console.log(`[TEACHER-04] URL after approve link: ${page.url()}`);
          } else {
            console.log('[TEACHER-04] No approve button found - teacher may auto-activate');
            bugs.push({
              page: page.url(), role: 'teacher', test: 'TEACHER-04: Admin Approval',
              error: 'No approve/accept button found for pending teacher',
              reproduction: `Log in as admin, go to /customadmin/pending/teachers/, find teacher ${teacher.username}`,
              console: [...consoleErrors],
            });
          }
        }
      } else {
        console.log('[TEACHER-04] Teacher not found in pending - may already be approved');
      }

      await takeScreenshot(page, 'TEACHER-04-admin-approval');
      await logState(page, 'TEACHER-04-final');
    } catch (e) {
      console.error(`[TEACHER-04] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-04: Admin Approval',
        error: e.message, reproduction: 'Admin approval of teacher',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-04-fail');
    }
  });

  test('TEACHER-04b: Login as Approved Teacher', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!teacher) throw new Error('No teacher credentials');
      console.log(`[TEACHER-04b] Logging in as approved teacher: ${teacher.username}`);

      await navigateAndWait(page, '/teacher/login/');
      await logState(page, 'TEACHER-04b-login');

      await tryFill(page, '#username', teacher.username);
      await tryFill(page, '#password', teacher.password);
      const loginBtn = page.locator('#loginBtn, button[type="submit"]').first();
      await loginBtn.click();
      await page.waitForTimeout(3000);

      const currentUrl = page.url();
      console.log(`[TEACHER-04b] URL after login: ${currentUrl}`);

      const loggedIn = currentUrl.includes('/dashboard/') || currentUrl.includes('/teacher/dashboard/');
      if (loggedIn) {
        console.log('[TEACHER-04b] SUCCESS: Teacher logged in successfully');
      } else if (currentUrl.includes('/login/') || currentUrl.includes('/teacher/login/')) {
        console.log('[TEACHER-04b] Still on login page - login may have failed');
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-04b: Approved Login',
          error: 'Teacher login failed after admin approval',
          reproduction: 'Log in as approved teacher',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-04b-approved-login');
      await logState(page, 'TEACHER-04b-final');
    } catch (e) {
      console.error(`[TEACHER-04b] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-04b: Approved Login',
        error: e.message, reproduction: 'Login as approved teacher',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-04b-fail');
    }
  });

  test('TEACHER-04c: Teacher Dashboard Loads', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-04c] Verifying teacher dashboard loads');
      await navigateAndWait(page, '/teacher/dashboard/');
      await logState(page, 'TEACHER-04c-dashboard');

      const currentUrl = page.url();
      if (currentUrl.includes('/login/')) {
        if (!teacher) throw new Error('No teacher credentials to re-login');
        await tryFill(page, '#username', teacher.username);
        await tryFill(page, '#password', teacher.password);
        const loginBtn = page.locator('#loginBtn, button[type="submit"]').first();
        await loginBtn.click();
        await page.waitForTimeout(3000);
        await navigateAndWait(page, '/teacher/dashboard/');
        await page.waitForTimeout(2000);
      }

      const dashUrl = page.url();
      console.log(`[TEACHER-04c] Dashboard URL: ${dashUrl}`);

      const heading = await page.locator('h1, h2, .dashboard-title, [class*="dashboard"] h1, [class*="dashboard"] h2').first().textContent().catch(() => 'not found');
      console.log(`[TEACHER-04c] Dashboard heading: ${heading}`);

      const hasContent = await page.locator('a, button, .card, .stat, .widget').count();
      console.log(`[TEACHER-04c] Dashboard interactive elements: ${hasContent}`);

      if (hasContent === 0 && dashUrl.includes('/dashboard/')) {
        bugs.push({
          page: dashUrl, role: 'teacher', test: 'TEACHER-04c: Dashboard Content',
          error: 'Dashboard loaded but no interactive elements found (empty page)',
          reproduction: 'Navigate to /teacher/dashboard/ as authenticated teacher',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-04c-dashboard');
      await logState(page, 'TEACHER-04c-final');
    } catch (e) {
      console.error(`[TEACHER-04c] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-04c: Dashboard Content',
        error: e.message, reproduction: 'Check teacher dashboard loads',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-04c-fail');
    }
  });

  // ===================================================================
  // TEACHER-05: PROFILE
  // ===================================================================
  test('TEACHER-05a: View Profile', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-05a] Viewing teacher profile');
      const navOk = await navigateAndWait(page, '/profile/');
      if (!navOk) {
        if (!teacher) throw new Error('No teacher credentials');
        await navigateAndWait(page, '/teacher/login/');
        await tryFill(page, '#username', teacher.username);
        await tryFill(page, '#password', teacher.password);
        const loginBtn = page.locator('#loginBtn, button[type="submit"]').first();
        await loginBtn.click();
        await page.waitForTimeout(2000);
        await navigateAndWait(page, '/profile/');
      }
      await logState(page, 'TEACHER-05a-profile');

      const currentUrl = page.url();
      console.log(`[TEACHER-05a] Profile URL: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[TEACHER-05a] Redirected to login - authentication required');
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-05a: View Profile',
          error: 'Profile page redirected to login despite being authenticated',
          reproduction: 'Navigate to /profile/',
          console: [...consoleErrors],
        });
      } else if (currentUrl.includes('/profile/')) {
        const profileContent = await page.locator('h1, h2, .profile-name, .user-name, [class*="profile"]').first().textContent().catch(() => 'not found');
        console.log(`[TEACHER-05a] Profile heading: ${profileContent}`);
      }

      await takeScreenshot(page, 'TEACHER-05a-profile');
      await logState(page, 'TEACHER-05a-final');
    } catch (e) {
      console.error(`[TEACHER-05a] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-05a: View Profile',
        error: e.message, reproduction: 'Navigate to /profile/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-05a-fail');
    }
  });

  test('TEACHER-05b: Edit Profile', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-05b] Viewing profile edit page');
      await navigateAndWait(page, '/profile/edit/');
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-05b-edit-profile');

      const currentUrl = page.url();
      console.log(`[TEACHER-05b] Edit profile URL: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[TEACHER-05b] Redirected to login');
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-05b: Edit Profile',
          error: 'Profile edit page not accessible',
          reproduction: 'Navigate to /profile/edit/',
          console: [...consoleErrors],
        });
      } else if (currentUrl.includes('/profile/edit/')) {
        const formFields = await page.locator('input, select, textarea').count();
        console.log(`[TEACHER-05b] Form fields count: ${formFields}`);

        const hasSaveBtn = await checkElementExists(page, 'button[type="submit"], .btn-save, input[type="submit"]');
        console.log(`[TEACHER-05b] Save button present: ${hasSaveBtn}`);

        if (formFields === 0) {
          bugs.push({
            page: currentUrl, role: 'teacher', test: 'TEACHER-05b: Edit Profile',
            error: 'Profile edit form has no input fields',
            reproduction: 'Navigate to /profile/edit/',
            console: [...consoleErrors],
          });
        }
      }

      await takeScreenshot(page, 'TEACHER-05b-edit-profile');
      await logState(page, 'TEACHER-05b-final');
    } catch (e) {
      console.error(`[TEACHER-05b] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-05b: Edit Profile',
        error: e.message, reproduction: 'Navigate to /profile/edit/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-05b-fail');
    }
  });

  // ===================================================================
  // TEACHER-06: CREATE COURSE
  // ===================================================================
  test('TEACHER-06: Create Course', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-06] Creating new course');
      await navigateAndWait(page, '/teacher/courses/create/');
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-06-create-course');

      const currentUrl = page.url();
      if (currentUrl.includes('/login/')) {
        if (!teacher) throw new Error('No teacher credentials');
        await tryFill(page, '#username', teacher.username);
        await tryFill(page, '#password', teacher.password);
        const loginBtn = page.locator('#loginBtn, button[type="submit"]').first();
        await loginBtn.click();
        await page.waitForTimeout(2000);
        await navigateAndWait(page, '/teacher/courses/create/');
        await page.waitForTimeout(1500);
      }

      await logState(page, 'TEACHER-06-create-form');

      const ts = timestamp();
      await tryFill(page, '#title, input[name="title"]', `Test Course ${ts}`);
      await tryFill(page, '#description, textarea[name="description"]', `Description for test course ${ts}`);
      await tryFill(page, '#category, select[name="category"]', 'Computer Science');
      await tryFill(page, '#price, input[name="price"]', '0');
      await tryFill(page, '#duration, input[name="duration"]', '4 weeks');

      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      const imgUploadBtn = page.locator('#image-label, [for="image"], .upload-label, #upload-image-btn').first();
      if (await imgUploadBtn.count() > 0) {
        await imgUploadBtn.click();
        const fileChooser = await fileChooserPromise;
        if (fileChooser) {
          const testImg = path.join(__dirname, '..', '..', 'static', 'img', 'default-course.png');
          await fileChooser.setFiles([testImg]).catch(() => {
            console.log('[TEACHER-06] Could not set image file (may not exist)');
          });
        }
      }

      await page.waitForTimeout(500);
      const submitBtn = page.locator('button[type="submit"], input[type="submit"], .btn-submit, #submit-btn').first();
      await submitBtn.click();
      await page.waitForTimeout(3000);

      const postUrl = page.url();
      console.log(`[TEACHER-06] URL after course creation: ${postUrl}`);

      const bodyText = await page.locator('body').textContent().catch(() => '');
      const successMsg = bodyText.includes('success') || bodyText.includes('created') || bodyText.includes('Course');
      console.log(`[TEACHER-06] Success indicator: ${successMsg}`);

      const uidMatch = postUrl.match(/([a-f0-9\-]{36})/i);
      if (uidMatch) {
        courseUid = uidMatch[1];
        console.log(`[TEACHER-06] Extracted course UID: ${courseUid}`);
      } else {
        console.log('[TEACHER-06] Could not extract course UID from URL');
      }

      if (!successMsg && (postUrl.includes('/create/') || postUrl.includes('/courses/'))) {
        const errors = await page.locator('.alert, .error, .validation-card.error, [class*="error"]').allTextContents().catch(() => []);
        console.log(`[TEACHER-06] Errors: ${JSON.stringify(errors)}`);
        bugs.push({
          page: postUrl, role: 'teacher', test: 'TEACHER-06: Create Course',
          error: 'Course creation may have failed',
          reproduction: 'Fill course creation form and submit',
          console: [...consoleErrors],
          details: errors,
        });
      }

      await takeScreenshot(page, 'TEACHER-06-create-result');
      await logState(page, 'TEACHER-06-final');
    } catch (e) {
      console.error(`[TEACHER-06] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-06: Create Course',
        error: e.message, reproduction: 'Create a new course',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-06-fail');
    }
  });

  // ===================================================================
  // TEACHER-07: VIEW MY COURSES
  // ===================================================================
  test('TEACHER-07: View My Courses', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-07] Viewing my courses');
      await navigateAndWait(page, '/teacher/courses/');
      await page.waitForTimeout(2000);
      await logState(page, 'TEACHER-07-my-courses');

      const courseCards = await page.locator('.course-card, .card, [class*="course"]').count();
      console.log(`[TEACHER-07] Course cards found: ${courseCards}`);

      const hasCreateBtn = await checkElementExists(page, 'a:has-text("Create"), a:has-text("New"), .btn-create, .btn-new');
      console.log(`[TEACHER-07] Create button present: ${hasCreateBtn}`);

      if (courseCards === 0) {
        bugs.push({
          page: page.url(), role: 'teacher', test: 'TEACHER-07: My Courses',
          error: 'No courses displayed in My Courses page',
          reproduction: 'Navigate to /teacher/courses/',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-07-my-courses');
      await logState(page, 'TEACHER-07-final');
    } catch (e) {
      console.error(`[TEACHER-07] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-07: My Courses',
        error: e.message, reproduction: 'Navigate to /teacher/courses/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-07-fail');
    }
  });

  // ===================================================================
  // TEACHER-08: EDIT COURSE
  // ===================================================================
  test('TEACHER-08: Edit Course', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!courseUid) {
        console.log('[TEACHER-08] No course UID available, attempting to find one');
        await navigateAndWait(page, '/teacher/courses/');
        await page.waitForTimeout(1500);

        const editLinks = page.locator('a[href*="edit"]');
        const count = await editLinks.count();
        if (count > 0) {
          const href = await editLinks.first().getAttribute('href');
          const uidMatch = href.match(/([a-f0-9\-]{36})/i);
          if (uidMatch) courseUid = uidMatch[1];
          console.log(`[TEACHER-08] Found course UID from edit link: ${courseUid}`);
        } else {
          throw new Error('Could not find any course to edit, and no courseUid from creation');
        }
      }

      const editUrl = `/teacher/courses/${courseUid}/edit/`;
      console.log(`[TEACHER-08] Navigating to ${editUrl}`);
      await navigateAndWait(page, editUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-08-edit-course');

      const currentUrl = page.url();
      const onEditPage = currentUrl.includes('/edit/');
      console.log(`[TEACHER-08] On edit page: ${onEditPage}`);

      if (onEditPage) {
        const titleField = page.locator('#title, input[name="title"]').first();
        if (await titleField.count() > 0) {
          const currentTitle = await titleField.inputValue().catch(() => '');
          console.log(`[TEACHER-08] Current title: ${currentTitle}`);
          await tryFill(page, '#title, input[name="title"]', `Updated ${currentTitle || 'Course'} ${timestamp()}`);
        }

        const submitBtn = page.locator('button[type="submit"], input[type="submit"], .btn-submit, #submit-btn').first();
        if (await submitBtn.count() > 0) {
          await submitBtn.click();
          await page.waitForTimeout(2000);
          console.log(`[TEACHER-08] URL after update: ${page.url()}`);
        } else {
          console.log('[TEACHER-08] No submit button found on edit page');
          bugs.push({
            page: currentUrl, role: 'teacher', test: 'TEACHER-08: Edit Course',
            error: 'No submit button found on edit page',
            reproduction: 'Navigate to course edit page',
            console: [...consoleErrors],
          });
        }
      } else {
        console.log(`[TEACHER-08] Not on edit page (redirected to: ${currentUrl})`);
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-08: Edit Course',
          error: `Edit page not accessible, redirected to ${currentUrl}`,
          reproduction: `Navigate to /teacher/courses/${courseUid}/edit/`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-08-edit-result');
      await logState(page, 'TEACHER-08-final');
    } catch (e) {
      console.error(`[TEACHER-08] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-08: Edit Course',
        error: e.message, reproduction: 'Edit a course',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-08-fail');
    }
  });

  // ===================================================================
  // TEACHER-09: DELETE COURSE (Cancel - we keep the course for lessons)
  // ===================================================================
  test('TEACHER-09: Delete Course (Prep - Note: Cancelled to preserve for lessons)', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!courseUid) {
        console.log('[TEACHER-09] No course UID available, skipping');
        return;
      }
      console.log('[TEACHER-09] Checking delete course page exists (not executing delete)');
      const deleteUrl = `/teacher/courses/${courseUid}/delete/`;
      await navigateAndWait(page, deleteUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-09-delete-page');

      const currentUrl = page.url();
      const onDeletePage = currentUrl.includes('/delete/');
      console.log(`[TEACHER-09] On delete page: ${onDeletePage}`);

      const hasConfirm = await checkElementExists(page, 'button:has-text("Confirm"), button:has-text("Delete"), a:has-text("Confirm"), a:has-text("Delete"), .btn-danger, .btn-confirm');
      console.log(`[TEACHER-09] Confirm delete button present: ${hasConfirm}`);

      if (!onDeletePage && !currentUrl.includes('/login/')) {
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-09: Delete Course',
          error: `Delete page not accessible, redirected to ${currentUrl}`,
          reproduction: `Navigate to /teacher/courses/${courseUid}/delete/`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-09-delete-check');
      await logState(page, 'TEACHER-09-final');
    } catch (e) {
      console.error(`[TEACHER-09] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-09: Delete Course',
        error: e.message, reproduction: 'Check delete course page',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-09-fail');
    }
  });

  // ===================================================================
  // TEACHER-10: COURSE LESSONS PAGE
  // ===================================================================
  test('TEACHER-10: Course Lessons Page', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!courseUid) throw new Error('No course UID');
      const lessonsUrl = `/teacher/courses/${courseUid}/lessons/`;
      console.log(`[TEACHER-10] Navigating to ${lessonsUrl}`);
      await navigateAndWait(page, lessonsUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-10-lessons');

      const addBtn = await checkElementExists(page, 'a:has-text("Add"), a:has-text("New"), .btn-add, .btn-new, .btn-lesson');
      console.log(`[TEACHER-10] Add lesson button present: ${addBtn}`);

      const lessonCount = await page.locator('.lesson-item, .lesson-card, tr, li, .card').count();
      console.log(`[TEACHER-10] Lesson items count: ${lessonCount}`);

      await takeScreenshot(page, 'TEACHER-10-lessons');
      await logState(page, 'TEACHER-10-final');
    } catch (e) {
      console.error(`[TEACHER-10] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-10: Course Lessons',
        error: e.message, reproduction: `Navigate to /teacher/courses/${courseUid}/lessons/`,
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-10-fail');
    }
  });

  // ===================================================================
  // TEACHER-11: ADD LESSON
  // ===================================================================
  test('TEACHER-11: Add Lesson', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!courseUid) throw new Error('No course UID');
      const addLessonUrl = `/teacher/courses/${courseUid}/lessons/add/`;
      console.log(`[TEACHER-11] Navigating to ${addLessonUrl}`);
      await navigateAndWait(page, addLessonUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-11-add-lesson');

      const currentUrl = page.url();
      if (currentUrl.includes('/login/')) {
        console.log('[TEACHER-11] Redirected to login - need to re-auth');
        throw new Error('Authentication required for adding lesson');
      }

      const ts = timestamp();
      await tryFill(page, '#title, input[name="title"]', `Test Lesson ${ts}`);
      await tryFill(page, '#description, textarea[name="description"]', `Lesson description ${ts}`);

      const videoField = page.locator('#video_url, #youtube_url, input[name="video_url"], input[name="youtube_url"]').first();
      if (await videoField.count() > 0) {
        await videoField.fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ');
        console.log('[TEACHER-11] Video URL filled');
      }

      const submitBtn = page.locator('button[type="submit"], input[type="submit"], .btn-submit, #submit-btn').first();
      await submitBtn.click();
      await page.waitForTimeout(3000);

      const postUrl = page.url();
      console.log(`[TEACHER-11] URL after lesson creation: ${postUrl}`);

      const bodyText = await page.locator('body').textContent().catch(() => '');
      const hasSuccess = bodyText.toLowerCase().includes('success') || bodyText.toLowerCase().includes('lesson') && bodyText.toLowerCase().includes('created');

      const uidMatch = postUrl.match(/([a-f0-9\-]{36})/i);
      if (uidMatch && (!courseUid || courseUid !== uidMatch[1])) {
        lessonUid = uidMatch[1];
        console.log(`[TEACHER-11] Extracted lesson UID: ${lessonUid}`);
      } else {
        const pageText = await page.locator('body').textContent().catch(() => '');
        const allUids = pageText.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/g);
        if (allUids) {
          const nonCourseUids = allUids.filter(u => u !== courseUid);
          if (nonCourseUids.length > 0) {
            lessonUid = nonCourseUids[0];
            console.log(`[TEACHER-11] Extracted lesson UID from page: ${lessonUid}`);
          }
        }
        console.log('[TEACHER-11] Could not extract lesson UID');
      }

      if (!hasSuccess && !postUrl.includes('/lessons/')) {
        bugs.push({
          page: postUrl, role: 'teacher', test: 'TEACHER-11: Add Lesson',
          error: 'Lesson creation may have failed',
          reproduction: `Navigate to ${addLessonUrl}, fill form, submit`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-11-add-result');
      await logState(page, 'TEACHER-11-final');
    } catch (e) {
      console.error(`[TEACHER-11] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-11: Add Lesson',
        error: e.message, reproduction: 'Add a lesson to course',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-11-fail');
    }
  });

  // ===================================================================
  // TEACHER-12: VIEW LESSONS AFTER ADD
  // ===================================================================
  test('TEACHER-12: View Lessons After Add', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!courseUid) throw new Error('No course UID');
      const lessonsUrl = `/teacher/courses/${courseUid}/lessons/`;
      await navigateAndWait(page, lessonsUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-12-lessons-after');

      const lessonItems = await page.locator('.lesson-item, .lesson-card, tr, li, .card').count();
      console.log(`[TEACHER-12] Lesson count after adding: ${lessonItems}`);

      if (lessonItems === 0) {
        bugs.push({
          page: page.url(), role: 'teacher', test: 'TEACHER-12: View Lessons',
          error: 'No lessons found after adding one',
          reproduction: `Navigate to ${lessonsUrl}`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-12-lessons-after');
      await logState(page, 'TEACHER-12-final');
    } catch (e) {
      console.error(`[TEACHER-12] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-12: View Lessons',
        error: e.message, reproduction: 'View lessons page',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-12-fail');
    }
  });

  // ===================================================================
  // TEACHER-13: EDIT LESSON
  // ===================================================================
  test('TEACHER-13: Edit Lesson', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      let targetLessonUid = lessonUid;
      if (!targetLessonUid && courseUid) {
        const lessonsUrl = `/teacher/courses/${courseUid}/lessons/`;
        await navigateAndWait(page, lessonsUrl);
        await page.waitForTimeout(1500);
        const editLinks = page.locator('a[href*="lesson"][href*="edit"], a[href*="lessons"][href*="edit"]');
        const count = await editLinks.count();
        if (count > 0) {
          const href = await editLinks.first().getAttribute('href');
          const uidMatch = href.match(/([a-f0-9\-]{36})/i);
          if (uidMatch) targetLessonUid = uidMatch[1];
        }
      }

      if (!targetLessonUid) {
        console.log('[TEACHER-13] No lesson UID available, skipping edit');
        bugs.push({
          page: page.url(), role: 'teacher', test: 'TEACHER-13: Edit Lesson',
          error: 'Could not find lesson UID to edit',
          reproduction: 'Try to edit a lesson after creation',
          console: [...consoleErrors],
        });
        return;
      }

      const editUrl = `/teacher/lessons/${targetLessonUid}/edit/`;
      console.log(`[TEACHER-13] Navigating to ${editUrl}`);
      await navigateAndWait(page, editUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-13-edit-lesson');

      const currentUrl = page.url();
      const onEditPage = currentUrl.includes('/edit/');
      if (onEditPage) {
        const titleField = page.locator('#title, input[name="title"]').first();
        if (await titleField.count() > 0) {
          const currentTitle = await titleField.inputValue().catch(() => '');
          console.log(`[TEACHER-13] Current lesson title: ${currentTitle}`);
          await tryFill(page, '#title, input[name="title"]', `Updated Lesson ${timestamp()}`);
        }

        const submitBtn = page.locator('button[type="submit"], input[type="submit"], .btn-submit, #submit-btn').first();
        if (await submitBtn.count() > 0) {
          await submitBtn.click();
          await page.waitForTimeout(2000);
          console.log(`[TEACHER-13] URL after update: ${page.url()}`);
        }
      } else {
        console.log(`[TEACHER-13] Not on edit page: ${currentUrl}`);
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-13: Edit Lesson',
          error: `Edit lesson page not accessible at ${editUrl}`,
          reproduction: `Navigate to ${editUrl}`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-13-edit-result');
      await logState(page, 'TEACHER-13-final');
    } catch (e) {
      console.error(`[TEACHER-13] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-13: Edit Lesson',
        error: e.message, reproduction: 'Edit a lesson',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-13-fail');
    }
  });

  // ===================================================================
  // TEACHER-14: DELETE LESSON
  // ===================================================================
  test('TEACHER-14: Delete Lesson Page Check', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      let targetLessonUid = lessonUid;
      if (!targetLessonUid && courseUid) {
        const lessonsUrl = `/teacher/courses/${courseUid}/lessons/`;
        await navigateAndWait(page, lessonsUrl);
        await page.waitForTimeout(1500);
        const deleteLinks = page.locator('a[href*="lessons"][href*="delete"], a[href*="lesson"][href*="delete"], a[href*="delete"]');
        const count = await deleteLinks.count();
        if (count > 0) {
          const href = await deleteLinks.first().getAttribute('href');
          const uidMatch = href.match(/([a-f0-9\-]{36})/i);
          if (uidMatch) targetLessonUid = uidMatch[1];
        }
      }

      if (!targetLessonUid) {
        console.log('[TEACHER-14] No lesson UID available, skipping');
        return;
      }

      const deleteUrl = `/teacher/lessons/${targetLessonUid}/delete/`;
      console.log(`[TEACHER-14] Checking ${deleteUrl}`);
      await navigateAndWait(page, deleteUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-14-delete-lesson');

      const currentUrl = page.url();
      const onDeletePage = currentUrl.includes('/delete/');
      console.log(`[TEACHER-14] On delete page: ${onDeletePage}`);

      const hasConfirm = await checkElementExists(page, 'button:has-text("Confirm"), button:has-text("Delete"), a:has-text("Confirm"), .btn-danger');
      console.log(`[TEACHER-14] Confirm delete present: ${hasConfirm}`);

      if (!onDeletePage && !currentUrl.includes('/login/')) {
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-14: Delete Lesson',
          error: `Delete page not accessible, redirected to ${currentUrl}`,
          reproduction: `Navigate to ${deleteUrl}`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-14-delete-check');
      await logState(page, 'TEACHER-14-final');
    } catch (e) {
      console.error(`[TEACHER-14] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-14: Delete Lesson',
        error: e.message, reproduction: 'Check delete lesson page',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-14-fail');
    }
  });

  // ===================================================================
  // TEACHER-15: LESSON LIST VERIFICATION
  // ===================================================================
  test('TEACHER-15: Lesson List Verification', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!courseUid) throw new Error('No course UID');
      const lessonsUrl = `/teacher/courses/${courseUid}/lessons/`;
      await navigateAndWait(page, lessonsUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-15-lesson-list');

      const lessonElements = await page.locator('a, button, .lesson-item, .lesson-card, td, span').allTextContents().catch(() => []);
      const hasLessonTitle = lessonElements.some(t => t.includes('Lesson') || t.includes('lesson'));
      console.log(`[TEACHER-15] Lesson title found on page: ${hasLessonTitle}`);

      const editLinks = page.locator('a[href*="edit"]');
      const deleteLinks = page.locator('a[href*="delete"]');
      console.log(`[TEACHER-15] Edit links: ${await editLinks.count()}, Delete links: ${await deleteLinks.count()}`);

      await takeScreenshot(page, 'TEACHER-15-lesson-list');
      await logState(page, 'TEACHER-15-final');
    } catch (e) {
      console.error(`[TEACHER-15] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-15: Lesson List',
        error: e.message, reproduction: 'Verify lesson list has content',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-15-fail');
    }
  });

  // ===================================================================
  // TEACHER-16: RESOURCE UPLOAD
  // ===================================================================
  test('TEACHER-16: Add Resource to Course', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!courseUid) throw new Error('No course UID');
      const resourceUrl = `/course/${courseUid}/resource/add/`;
      console.log(`[TEACHER-16] Navigating to ${resourceUrl}`);
      await navigateAndWait(page, resourceUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-16-add-resource');

      const currentUrl = page.url();
      if (currentUrl.includes('/login/') && !currentUrl.includes('/resource/add/')) {
        console.log('[TEACHER-16] Redirected to login - need to re-auth');
        throw new Error('Authentication required');
      }

      await tryFill(page, '#title, input[name="title"]', `Test Resource ${timestamp()}`);
      await tryFill(page, '#description, textarea[name="description"]', 'Resource description');

      const categoryField = page.locator('#category, select[name="category"]').first();
      if (await categoryField.count() > 0) {
        const options = await categoryField.locator('option').allTextContents().catch(() => []);
        console.log(`[TEACHER-16] Category options: ${JSON.stringify(options)}`);
        if (options.length > 1) {
          await categoryField.selectOption(options[1]);
        } else {
          await categoryField.selectOption(options[0]);
        }
      }

      const pdfPath = getTestPdfPath();
      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      const uploadBtn = page.locator('#file-label, [for="file"], .upload-label, #file-input-label, label[for*="file"]').first();
      if (await uploadBtn.count() > 0) {
        await uploadBtn.click();
        const fileChooser = await fileChooserPromise;
        if (fileChooser) {
          await fileChooser.setFiles([pdfPath]);
          console.log('[TEACHER-16] PDF selected for resource');
        }
      } else {
        await page.setInputFiles('input[type="file"]', pdfPath).catch(e => {
          console.log(`[TEACHER-16] Direct file input failed: ${e.message}`);
        });
      }

      await page.waitForTimeout(500);
      const submitBtn = page.locator('button[type="submit"], input[type="submit"], .btn-submit, #submit-btn').first();
      await submitBtn.click();
      await page.waitForTimeout(3000);

      const postUrl = page.url();
      console.log(`[TEACHER-16] URL after resource add: ${postUrl}`);

      const bodyText = await page.locator('body').textContent().catch(() => '');
      const hasSuccess = bodyText.toLowerCase().includes('success') || bodyText.toLowerCase().includes('resource') || bodyText.toLowerCase().includes('uploaded');

      const uidMatch = postUrl.match(/([a-f0-9\-]{36})/i);
      if (uidMatch) {
        resourceUid = uidMatch[1];
        console.log(`[TEACHER-16] Resource UID: ${resourceUid}`);
      }

      if (!hasSuccess) {
        const errors = await page.locator('.alert, .error, .validation-card.error, [class*="error"]').allTextContents().catch(() => []);
        console.log(`[TEACHER-16] Errors: ${JSON.stringify(errors)}`);
        bugs.push({
          page: postUrl, role: 'teacher', test: 'TEACHER-16: Resource Upload',
          error: 'Resource upload may have failed',
          reproduction: `Navigate to ${resourceUrl}, fill form, upload PDF, submit`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-16-resource-result');
      await logState(page, 'TEACHER-16-final');
    } catch (e) {
      console.error(`[TEACHER-16] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-16: Resource Upload',
        error: e.message, reproduction: 'Upload a resource to the course',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-16-fail');
    }
  });

  // ===================================================================
  // TEACHER-17: SUBMIT COURSE FOR APPROVAL
  // ===================================================================
  test('TEACHER-17: Submit Course for Approval', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      if (!courseUid) throw new Error('No course UID');
      const submitUrl = `/teacher/courses/${courseUid}/submit/`;
      console.log(`[TEACHER-17] Navigating to ${submitUrl}`);
      await navigateAndWait(page, submitUrl);
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-17-submit-approval');

      const currentUrl = page.url();
      const onSubmitPage = currentUrl.includes('/submit/');

      const bodyText = await page.locator('body').textContent().catch(() => '');
      const hasSubmitForm = await checkElementExists(page, 'button[type="submit"], input[type="submit"], a:has-text("Submit"), a:has-text("Confirm"), .btn-submit, .btn-confirm');

      if (onSubmitPage && hasSubmitForm) {
        const confirmBtn = page.locator('button[type="submit"], input[type="submit"], a:has-text("Submit"), a:has-text("Confirm"), .btn-submit, .btn-confirm').first();
        await confirmBtn.click();
        await page.waitForTimeout(3000);
        console.log(`[TEACHER-17] URL after submission: ${page.url()}`);

        const resultText = await page.locator('body').textContent().catch(() => '');
        const wasSubmitted = resultText.toLowerCase().includes('success') || resultText.toLowerCase().includes('submitted') || resultText.toLowerCase().includes('pending') || resultText.toLowerCase().includes('approval');
        console.log(`[TEACHER-17] Submission acknowledged: ${wasSubmitted}`);
      } else if (currentUrl.includes('/login/')) {
        console.log('[TEACHER-17] Redirected to login');
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-17: Submit Approval',
          error: 'Submit for approval page requires authentication',
          reproduction: `Navigate to ${submitUrl}`,
          console: [...consoleErrors],
        });
      } else if (!onSubmitPage) {
        console.log(`[TEACHER-17] Redirected to: ${currentUrl} (may already be submitted)`);
        const alreadySubmitted = bodyText.toLowerCase().includes('pending') || bodyText.toLowerCase().includes('submitted') || bodyText.toLowerCase().includes('approval');
        if (!alreadySubmitted) {
          bugs.push({
            page: currentUrl, role: 'teacher', test: 'TEACHER-17: Submit Approval',
            error: `Submit page not accessible, redirected to ${currentUrl}`,
            reproduction: `Navigate to ${submitUrl}`,
            console: [...consoleErrors],
          });
        }
      }

      await takeScreenshot(page, 'TEACHER-17-submit-result');
      await logState(page, 'TEACHER-17-final');
    } catch (e) {
      console.error(`[TEACHER-17] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-17: Submit Approval',
        error: e.message, reproduction: 'Submit course for approval',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-17-fail');
    }
  });

  // ===================================================================
  // TEACHER-18: PERMISSION CHECKS
  // ===================================================================
  test('TEACHER-18: Permission Checks - Blocked Admin URLs', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    const permissionResults = [];

    try {
      // 18a: Admin dashboard
      console.log('[TEACHER-18a] Accessing /customadmin/dashboard/');
      await navigateAndWait(page, '/customadmin/dashboard/');
      let url = page.url();
      let blocked = url.includes('/portal-secure-access/') || url.includes('/login/') || url.includes('?next=');
      permissionResults.push({ url: '/customadmin/dashboard/', blocked, finalUrl: url });
      console.log(`[TEACHER-18a] ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);
      await takeScreenshot(page, 'TEACHER-18a-admin-dashboard');

      // 18b: Admin pending users
      console.log('[TEACHER-18b] Accessing /customadmin/pending/');
      await navigateAndWait(page, '/customadmin/pending/');
      url = page.url();
      blocked = url.includes('/portal-secure-access/') || url.includes('/login/');
      permissionResults.push({ url: '/customadmin/pending/', blocked, finalUrl: url });
      console.log(`[TEACHER-18b] ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);

      // 18c: Admin students
      console.log('[TEACHER-18c] Accessing /customadmin/students/');
      await navigateAndWait(page, '/customadmin/students/');
      url = page.url();
      blocked = url.includes('/portal-secure-access/') || url.includes('/login/');
      permissionResults.push({ url: '/customadmin/students/', blocked, finalUrl: url });
      console.log(`[TEACHER-18c] ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);

      // 18d: Admin teachers
      console.log('[TEACHER-18d] Accessing /customadmin/teachers/');
      await navigateAndWait(page, '/customadmin/teachers/');
      url = page.url();
      blocked = url.includes('/portal-secure-access/') || url.includes('/login/');
      permissionResults.push({ url: '/customadmin/teachers/', blocked, finalUrl: url });
      console.log(`[TEACHER-18d] ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);

      // 18e: Admin analytics
      console.log('[TEACHER-18e] Accessing /customadmin/analytics/');
      await navigateAndWait(page, '/customadmin/analytics/');
      url = page.url();
      blocked = url.includes('/portal-secure-access/') || url.includes('/login/');
      permissionResults.push({ url: '/customadmin/analytics/', blocked, finalUrl: url });
      console.log(`[TEACHER-18e] ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);

      // 18f: Admin pending teachers
      console.log('[TEACHER-18f] Accessing /customadmin/pending/teachers/');
      await navigateAndWait(page, '/customadmin/pending/teachers/');
      url = page.url();
      blocked = url.includes('/portal-secure-access/') || url.includes('/login/');
      permissionResults.push({ url: '/customadmin/pending/teachers/', blocked, finalUrl: url });
      console.log(`[TEACHER-18f] ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);

      // 18g: Admin portal access (hidden login)
      console.log('[TEACHER-18g] Accessing /customadmin/portal-secure-access/');
      await navigateAndWait(page, '/customadmin/portal-secure-access/');
      url = page.url();
      const onLoginPage = url.includes('/portal-secure-access/') || url.includes('/login/');
      permissionResults.push({ url: '/customadmin/portal-secure-access/', blocked: !onLoginPage, isLoginPage: onLoginPage, finalUrl: url });
      console.log(`[TEACHER-18g] Login page: ${onLoginPage} -> ${url}`);

      const allowedEndpoints = permissionResults.filter(r => !r.blocked && !r.url.includes('/portal-secure-access/'));
      if (allowedEndpoints.length > 0) {
        console.log(`[TEACHER-18] WARN: ${allowedEndpoints.length} admin endpoints were NOT blocked`);
        bugs.push({
          page: page.url(), role: 'teacher', test: 'TEACHER-18: Permission Checks',
          error: `Teacher was not blocked from admin URLs: ${allowedEndpoints.map(e => e.url).join(', ')}`,
          reproduction: 'Try accessing /customadmin/* URLs as teacher',
          console: [...consoleErrors],
          details: permissionResults,
        });
      } else {
        console.log('[TEACHER-18] SUCCESS: All admin URLs properly blocked');
      }

      await takeScreenshot(page, 'TEACHER-18-permissions');
      await logState(page, 'TEACHER-18-final');
    } catch (e) {
      console.error(`[TEACHER-18] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-18: Permission Checks',
        error: e.message, reproduction: 'Try accessing /customadmin/* URLs as teacher',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-18-fail');
    }
  });

  // ===================================================================
  // TEACHER-19: NOTIFICATIONS
  // ===================================================================
  test('TEACHER-19: Notifications', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-19] Accessing notifications page');
      await navigateAndWait(page, '/notifications/');
      await page.waitForTimeout(1500);
      await logState(page, 'TEACHER-19-notifications');

      const currentUrl = page.url();
      if (currentUrl.includes('/login/')) {
        if (!teacher) throw new Error('No teacher credentials');
        await tryFill(page, '#username', teacher.username);
        await tryFill(page, '#password', teacher.password);
        const loginBtn = page.locator('#loginBtn, button[type="submit"]').first();
        await loginBtn.click();
        await page.waitForTimeout(2000);
        await navigateAndWait(page, '/notifications/');
        await page.waitForTimeout(1500);
      }

      if (page.url().includes('/notifications/')) {
        const notifItems = await page.locator('.notif-item, .notification-item, li, .card .item, tr').count();
        console.log(`[TEACHER-19] Notification items: ${notifItems}`);

        const hasUnread = await checkElementExists(page, '.unread, .notif-item.unread, [class*="unread"]');
        console.log(`[TEACHER-19] Unread present: ${hasUnread}`);

        const markAllReadBtn = await checkElementExists(page, 'a:has-text("Mark all"), button:has-text("Mark all"), a:has-text("Read all")');
        console.log(`[TEACHER-19] Mark all read button: ${markAllReadBtn}`);
      } else {
        console.log(`[TEACHER-19] Not on notifications page: ${page.url()}`);
        bugs.push({
          page: page.url(), role: 'teacher', test: 'TEACHER-19: Notifications',
          error: 'Notifications page not accessible',
          reproduction: 'Navigate to /notifications/',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-19-notifications');
      await logState(page, 'TEACHER-19-final');
    } catch (e) {
      console.error(`[TEACHER-19] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-19: Notifications',
        error: e.message, reproduction: 'Navigate to /notifications/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-19-fail');
    }
  });

  // ===================================================================
  // TEACHER-20: LOGOUT
  // ===================================================================
  test('TEACHER-20: Logout Flow', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    try {
      console.log('[TEACHER-20] Attempting logout');
      await navigateAndWait(page, '/logout/');
      await page.waitForTimeout(2000);
      await logState(page, 'TEACHER-20-logout');

      const currentUrl = page.url();
      console.log(`[TEACHER-20] URL after logout: ${currentUrl}`);

      const redirectedToLogin = currentUrl.includes('/login/') || currentUrl === BASE_URL + '/' || currentUrl === BASE_URL || currentUrl === '';
      console.log(`[TEACHER-20] Redirected to login: ${redirectedToLogin}`);

      if (!redirectedToLogin && !currentUrl.includes('/logout/')) {
        bugs.push({
          page: currentUrl, role: 'teacher', test: 'TEACHER-20: Logout',
          error: `Logout did not redirect to login page. Ended at: ${currentUrl}`,
          reproduction: 'Navigate to /logout/ and check redirect',
          console: [...consoleErrors],
        });
      }

      // Verify protected route redirects after logout
      await navigateAndWait(page, '/teacher/dashboard/');
      const postLogoutUrl = page.url();
      const protectedRedirected = postLogoutUrl.includes('/login/') || postLogoutUrl.includes('?next=');
      console.log(`[TEACHER-20] Post-logout dashboard access blocked: ${protectedRedirected} -> ${postLogoutUrl}`);

      if (!protectedRedirected && postLogoutUrl.includes('/dashboard/')) {
        bugs.push({
          page: postLogoutUrl, role: 'teacher', test: 'TEACHER-20: Logout Session',
          error: 'Dashboard still accessible after logout (session not destroyed)',
          reproduction: 'Logout, then navigate to /teacher/dashboard/',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'TEACHER-20-logout');
      await logState(page, 'TEACHER-20-final');
    } catch (e) {
      console.error(`[TEACHER-20] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(), role: 'teacher', test: 'TEACHER-20: Logout',
        error: e.message, reproduction: 'Navigate to /logout/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'TEACHER-20-fail');
    }
  });

  // Helper to reduce duplication
  async function logState(page, label) {
    return logPageState(page, label);
  }

  // ===================================================================
  // BUG REPORT SUMMARY - ALWAYS RUNS LAST
  // ===================================================================
  test('BUG REPORT SUMMARY', () => {
    console.log('========================================');
    console.log('TEACHER FLOW AUDIT COMPLETE');
    console.log('========================================');
    console.log('TEACHER FLOW BUGS FOUND:', bugs.length);
    console.log('========================================');

    if (bugs.length === 0) {
      console.log('  No bugs detected in Teacher Flow.');
    } else {
      bugs.forEach((b, i) => {
        console.log(`\nBug #${i + 1}: [${b.test}]`);
        console.log(`  URL: ${b.page}`);
        console.log(`  Error: ${b.error}`);
        console.log(`  Reproduction: ${b.reproduction}`);
        if (b.console && b.console.length > 0) {
          console.log(`  Console Errors (${b.console.length}):`);
          b.console.slice(0, 5).forEach((ce, ci) => console.log(`    [${ci}] ${ce}`));
        }
        if (b.details) {
          console.log(`  Details: ${JSON.stringify(b.details)}`);
        }
      });
    }

    console.log('\n========================================');
    console.log('END OF TEACHER FLOW BUG REPORT');
    console.log('========================================');
  });

});
