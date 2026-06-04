const { test, expect } = require('@playwright/test');
const path = require('path');
const {
  BASE_URL, timestamp, createStudentCredentials,
  navigateAndWait, waitForSelectorSafe, takeScreenshot,
  logPageState, collectConsoleErrors, tryClick, tryFill,
  checkElementExists, getTestPdfPath
} = require('./helpers');

const bugs = [];
let sharedStudent = null;

function setupConsoleCapture(page) {
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));
  page.on('requestfailed', req => errors.push(`NET: ${req.url()} ${req.failure()?.errorText}`));
  return errors;
}

test.describe('Student Flow - Full LMS Audit', () => {

  // ===================================================================
  // STUDENT-01: STUDENT SIGNUP
  // ===================================================================
  test('STUDENT-01: Student Signup - Create Account', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    const creds = createStudentCredentials();
    sharedStudent = creds;

    try {
      console.log(`[STUDENT-01] Creating student: ${creds.username} / ${creds.email}`);

      const navOk = await navigateAndWait(page, '/signup/');
      if (!navOk) throw new Error('Failed to navigate to /signup/');
      await logPageState(page, 'STUDENT-01-signup-page');

      await tryFill(page, '#username', creds.username);
      await tryFill(page, '#fullname', creds.fullName);
      await tryFill(page, '#email', creds.email);
      await tryFill(page, '#phone_number', creds.phone);

      const pdfPath = getTestPdfPath();
      console.log(`[STUDENT-01] Using PDF: ${pdfPath}`);

      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      await tryClick(page, '#upload-label');
      const fileChooser = await fileChooserPromise;
      if (fileChooser) {
        await fileChooser.setFiles([pdfPath]);
        console.log('[STUDENT-01] PDF selected');
      } else {
        console.log('[STUDENT-01] File chooser event not triggered, trying direct input');
        await page.setInputFiles('#proof_file', pdfPath).catch(e => {
          console.log(`[STUDENT-01] Direct file input failed: ${e.message}`);
        });
      }

      await tryFill(page, '#password', creds.password);
      await tryFill(page, '#confirm_password', creds.password);

      await page.waitForTimeout(500);
      await page.click('#signup-btn');
      console.log('[STUDENT-01] Signup form submitted');

      await page.waitForTimeout(3000);

      const currentUrl = page.url();
      console.log(`[STUDENT-01] URL after signup: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[STUDENT-01] SUCCESS: Redirected to login page');
        const successMsg = await page.locator('.alert-success, .toast-message, .messages .success, [class*="success"]').first().textContent().catch(() => 'not found');
        console.log(`[STUDENT-01] Success message: ${successMsg}`);
      } else if (currentUrl.includes('/signup/')) {
        const errorEls = await page.locator('.validation-card.error, .alert-error, .alert-danger, .toast-message, [class*="error"]').allTextContents().catch(() => []);
        console.log(`[STUDENT-01] Still on signup. Errors: ${JSON.stringify(errorEls)}`);
        const serverErrors = await page.locator('.validation-card.error ul li, .validation-card.error div, .alert ul li').allTextContents().catch(() => []);
        console.log(`[STUDENT-01] Server validation: ${JSON.stringify(serverErrors)}`);
      } else {
        console.log(`[STUDENT-01] Unexpected redirect to: ${currentUrl}`);
      }

      await takeScreenshot(page, 'STUDENT-01-signup-result');
      await logPageState(page, 'STUDENT-01-final');

    } catch (e) {
      console.error(`[STUDENT-01] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-01: Student Signup',
        error: e.message,
        reproduction: 'Navigate to /signup/, fill all fields with valid data, upload PDF, submit',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-01-fail');
    }
  });

  // ===================================================================
  // STUDENT-02: SIGNUP VALIDATION - EMPTY FORM
  // ===================================================================
  test('STUDENT-02: Signup Validation - Empty Form Submission', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-02] Testing empty form submission');
      await navigateAndWait(page, '/signup/');
      await logPageState(page, 'STUDENT-02-signup-page');

      await page.click('#signup-btn');
      await page.waitForTimeout(1500);

      const validationCards = await page.locator('.validation-card.error').count();
      console.log(`[STUDENT-02] Validation error cards found: ${validationCards}`);

      const errorTexts = await page.locator('.validation-card.error').allTextContents().catch(() => []);
      console.log(`[STUDENT-02] Error texts: ${JSON.stringify(errorTexts)}`);

      if (validationCards === 0) {
        const otherErrors = await page.locator('.alert, .error, [class*="error"], [class*="alert"], .toast-message').allTextContents().catch(() => []);
        console.log(`[STUDENT-02] Other error elements: ${JSON.stringify(otherErrors)}`);
        bugs.push({
          page: page.url(),
          role: 'student',
          test: 'STUDENT-02: Empty Form Validation',
          error: 'No validation error cards appeared for empty form submission',
          reproduction: 'Navigate to /signup/, click submit without filling any fields',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'STUDENT-02-empty-form');
      await logPageState(page, 'STUDENT-02-final');

    } catch (e) {
      console.error(`[STUDENT-02] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-02: Empty Form Validation',
        error: e.message,
        reproduction: 'Navigate to /signup/, click submit with empty form',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-02-fail');
    }
  });

  // ===================================================================
  // STUDENT-03: SIGNUP VALIDATION - INVALID EMAIL
  // ===================================================================
  test('STUDENT-03: Signup Validation - Invalid Email', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-03] Testing invalid email validation');
      await navigateAndWait(page, '/signup/');
      await logPageState(page, 'STUDENT-03-signup-page');

      await tryFill(page, '#username', `invalid_email_test_${timestamp()}`);
      await tryFill(page, '#fullname', 'Invalid Email Test');
      await tryFill(page, '#email', 'not-an-email');
      await tryFill(page, '#phone_number', '9876543210');
      await tryFill(page, '#password', 'TestPass123!');
      await tryFill(page, '#confirm_password', 'TestPass123!');

      const pdfPath = getTestPdfPath();
      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      await tryClick(page, '#upload-label');
      const fileChooser = await fileChooserPromise;
      if (fileChooser) {
        await fileChooser.setFiles([pdfPath]);
      } else {
        await page.setInputFiles('#proof_file', pdfPath).catch(() => {});
      }

      await page.click('#signup-btn');
      await page.waitForTimeout(1500);

      const emailError = await page.locator('.validation-card.error:has-text("email"), .validation-card.error:has-text("Email"), .validation-card.error:has-text("invalid"), .validation-card.error:has-text("Invalid")').count();
      console.log(`[STUDENT-03] Email validation error found: ${emailError > 0}`);

      const allErrors = await page.locator('.validation-card.error').allTextContents().catch(() => []);
      console.log(`[STUDENT-03] All errors: ${JSON.stringify(allErrors)}`);

      if (emailError === 0) {
        bugs.push({
          page: page.url(),
          role: 'student',
          test: 'STUDENT-03: Invalid Email Validation',
          error: 'No email validation error shown for "not-an-email"',
          reproduction: 'Fill signup form with invalid email "not-an-email", submit',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'STUDENT-03-invalid-email');
      await logPageState(page, 'STUDENT-03-final');

    } catch (e) {
      console.error(`[STUDENT-03] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-03: Invalid Email Validation',
        error: e.message,
        reproduction: 'Fill signup with invalid email "not-an-email", submit',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-03-fail');
    }
  });

  // ===================================================================
  // STUDENT-04: SIGNUP VALIDATION - DUPLICATE USERNAME
  // ===================================================================
  test('STUDENT-04: Signup Validation - Duplicate Username', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      const dupUsername = sharedStudent ? sharedStudent.username : `student_${timestamp()}`;
      console.log(`[STUDENT-04] Testing duplicate username: ${dupUsername}`);
      await navigateAndWait(page, '/signup/');
      await logPageState(page, 'STUDENT-04-signup-page');

      await tryFill(page, '#username', dupUsername);
      await tryFill(page, '#fullname', 'Duplicate Username Test');
      await tryFill(page, '#email', `dup_username_${timestamp()}@test.neolearner.com`);
      await tryFill(page, '#phone_number', '9876543210');

      const pdfPath = getTestPdfPath();
      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      await tryClick(page, '#upload-label');
      const fileChooser = await fileChooserPromise;
      if (fileChooser) {
        await fileChooser.setFiles([pdfPath]);
      } else {
        await page.setInputFiles('#proof_file', pdfPath).catch(() => {});
      }

      await tryFill(page, '#password', 'TestPass123!');
      await tryFill(page, '#confirm_password', 'TestPass123!');

      await page.click('#signup-btn');
      await page.waitForTimeout(3000);

      const currentUrl = page.url();
      console.log(`[STUDENT-04] URL after submission: ${currentUrl}`);

      const dupError = await page.locator('text=username, text=already, text=exists, text=taken, text=duplicate, .alert-error, .alert-danger, .validation-card.error').allTextContents().catch(() => []);
      console.log(`[STUDENT-04] Error messages: ${JSON.stringify(dupError)}`);

      const hasDuplicateError = dupError.some(t =>
        t.toLowerCase().includes('username') ||
        t.toLowerCase().includes('already') ||
        t.toLowerCase().includes('exists') ||
        t.toLowerCase().includes('taken') ||
        t.toLowerCase().includes('duplicate')
      );

      if (!hasDuplicateError && currentUrl.includes('/signup/')) {
        console.log('[STUDENT-04] WARN: Duplicate username may not have been caught');
        bugs.push({
          page: page.url(),
          role: 'student',
          test: 'STUDENT-04: Duplicate Username Validation',
          error: 'Duplicate username was not rejected with an error message',
          reproduction: `Try signing up with existing username "${dupUsername}"`,
          console: [...consoleErrors],
        });
      } else if (hasDuplicateError) {
        console.log('[STUDENT-04] SUCCESS: Duplicate username was properly rejected');
      }

      await takeScreenshot(page, 'STUDENT-04-dup-username');
      await logPageState(page, 'STUDENT-04-final');

    } catch (e) {
      console.error(`[STUDENT-04] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-04: Duplicate Username Validation',
        error: e.message,
        reproduction: 'Try signing up with an existing username',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-04-fail');
    }
  });

  // ===================================================================
  // STUDENT-05: SIGNUP VALIDATION - DUPLICATE EMAIL
  // ===================================================================
  test('STUDENT-05: Signup Validation - Duplicate Email', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      const dupEmail = sharedStudent ? sharedStudent.email : `student_${timestamp()}@test.neolearner.com`;
      console.log(`[STUDENT-05] Testing duplicate email: ${dupEmail}`);
      await navigateAndWait(page, '/signup/');
      await logPageState(page, 'STUDENT-05-signup-page');

      await tryFill(page, '#username', `dup_email_test_${timestamp()}`);
      await tryFill(page, '#fullname', 'Duplicate Email Test');
      await tryFill(page, '#email', dupEmail);
      await tryFill(page, '#phone_number', '9876543210');

      const pdfPath = getTestPdfPath();
      const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 10000 }).catch(() => null);
      await tryClick(page, '#upload-label');
      const fileChooser = await fileChooserPromise;
      if (fileChooser) {
        await fileChooser.setFiles([pdfPath]);
      } else {
        await page.setInputFiles('#proof_file', pdfPath).catch(() => {});
      }

      await tryFill(page, '#password', 'TestPass123!');
      await tryFill(page, '#confirm_password', 'TestPass123!');

      await page.click('#signup-btn');
      await page.waitForTimeout(3000);

      const dupError = await page.locator('text=email, text=already, text=exists, text=duplicate, .alert-error, .alert-danger, .validation-card.error').allTextContents().catch(() => []);
      console.log(`[STUDENT-05] Error messages: ${JSON.stringify(dupError)}`);

      const hasDuplicateError = dupError.some(t =>
        t.toLowerCase().includes('email') ||
        t.toLowerCase().includes('already') ||
        t.toLowerCase().includes('exists') ||
        t.toLowerCase().includes('duplicate')
      );

      if (!hasDuplicateError) {
        console.log('[STUDENT-05] WARN: Duplicate email may not have been caught');
        bugs.push({
          page: page.url(),
          role: 'student',
          test: 'STUDENT-05: Duplicate Email Validation',
          error: 'Duplicate email was not rejected with an error message',
          reproduction: `Try signing up with existing email "${dupEmail}"`,
          console: [...consoleErrors],
        });
      } else {
        console.log('[STUDENT-05] SUCCESS: Duplicate email was properly rejected');
      }

      await takeScreenshot(page, 'STUDENT-05-dup-email');
      await logPageState(page, 'STUDENT-05-final');

    } catch (e) {
      console.error(`[STUDENT-05] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-05: Duplicate Email Validation',
        error: e.message,
        reproduction: 'Try signing up with an existing email',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-05-fail');
    }
  });

  // ===================================================================
  // STUDENT-06: STUDENT LOGIN (PENDING ACCOUNT)
  // ===================================================================
  test('STUDENT-06: Student Login - Pending Account', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      const creds = sharedStudent || createStudentCredentials();
      console.log(`[STUDENT-06] Trying login with pending student: ${creds.username}`);

      await navigateAndWait(page, '/login/');
      await logPageState(page, 'STUDENT-06-login-page');

      const approvalNotice = await page.locator('text=approval, text=pending, text=wait, text=contact').count();
      console.log(`[STUDENT-06] Approval notice present: ${approvalNotice > 0}`);

      await tryFill(page, '#username', creds.username);
      await tryFill(page, '#password', creds.password);

      const loginBtn = page.locator('#loginBtn, button[type="submit"]').first();
      await loginBtn.click();
      await page.waitForTimeout(3000);

      const postLoginUrl = page.url();
      console.log(`[STUDENT-06] URL after login attempt: ${postLoginUrl}`);

      const pageContent = await page.locator('body').textContent().catch(() => '');
      const hasPendingMsg = pageContent.toLowerCase().includes('pending') ||
                            pageContent.toLowerCase().includes('approval') ||
                            pageContent.toLowerCase().includes('not approved') ||
                            pageContent.toLowerCase().includes('inactive') ||
                            pageContent.toLowerCase().includes('blocked');

      console.log(`[STUDENT-06] Pending message found: ${hasPendingMsg}`);

      if (postLoginUrl.includes('/dashboard/') || postLoginUrl.includes('/profile/')) {
        console.log('[STUDENT-06] NOTE: Pending student was able to login (may have been pre-approved)');
      } else if (!hasPendingMsg && postLoginUrl.includes('/login/')) {
        console.log('[STUDENT-06] Still on login page, no pending message shown');
        bugs.push({
          page: postLoginUrl,
          role: 'student',
          test: 'STUDENT-06: Pending Login',
          error: 'No pending-approval message displayed for unapproved student login attempt',
          reproduction: `Login with pending student "${creds.username}" at /login/`,
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'STUDENT-06-pending-login');
      await logPageState(page, 'STUDENT-06-final');

    } catch (e) {
      console.error(`[STUDENT-06] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-06: Pending Login',
        error: e.message,
        reproduction: 'Navigate to /login/, attempt login with pending student credentials',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-06-fail');
    }
  });

  // ===================================================================
  // STUDENT-07: DASHBOARD ACCESS
  // ===================================================================
  test('STUDENT-07: Dashboard Access', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-07] Attempting direct dashboard access');
      await navigateAndWait(page, '/dashboard/');
      await logPageState(page, 'STUDENT-07-dashboard-access');

      const currentUrl = page.url();
      console.log(`[STUDENT-07] Final URL: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[STUDENT-07] Redirected to login - expected if not authenticated');
      } else if (currentUrl.includes('/dashboard/')) {
        console.log('[STUDENT-07] SUCCESS: Dashboard loaded');
        const welcomeText = await page.locator('text=Welcome, text=Dashboard, text=My Courses').first().textContent().catch(() => 'not found');
        console.log(`[STUDENT-07] Dashboard content: ${welcomeText}`);
      } else {
        console.log(`[STUDENT-07] Unexpected location: ${currentUrl}`);
      }

      await takeScreenshot(page, 'STUDENT-07-dashboard');
      await logPageState(page, 'STUDENT-07-final');

    } catch (e) {
      console.error(`[STUDENT-07] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-07: Dashboard Access',
        error: e.message,
        reproduction: 'Navigate to /dashboard/ without authentication',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-07-fail');
    }
  });

  // ===================================================================
  // STUDENT-08: PROFILE VIEW
  // ===================================================================
  test('STUDENT-08: Profile View', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-08] Attempting profile view');
      await navigateAndWait(page, '/profile/');
      await logPageState(page, 'STUDENT-08-profile');

      const currentUrl = page.url();
      console.log(`[STUDENT-08] Profile URL: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[STUDENT-08] Redirected to login - authentication required');
      } else if (currentUrl.includes('/profile/')) {
        console.log('[STUDENT-08] Profile page loaded successfully');
        const profileContent = await page.locator('h1, h2, .profile-name, .user-name, [class*="profile"]').first().textContent().catch(() => 'not found');
        console.log(`[STUDENT-08] Profile heading: ${profileContent}`);
      }

      await takeScreenshot(page, 'STUDENT-08-profile');
      await logPageState(page, 'STUDENT-08-final');

    } catch (e) {
      console.error(`[STUDENT-08] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-08: Profile View',
        error: e.message,
        reproduction: 'Navigate to /profile/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-08-fail');
    }
  });

  // ===================================================================
  // STUDENT-09: PROFILE EDIT
  // ===================================================================
  test('STUDENT-09: Profile Edit Page', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-09] Attempting profile edit');
      await navigateAndWait(page, '/profile/edit/');
      await logPageState(page, 'STUDENT-09-edit-profile');

      const currentUrl = page.url();
      console.log(`[STUDENT-09] Edit profile URL: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[STUDENT-09] Redirected to login - authentication required');
      } else if (currentUrl.includes('/profile/edit/')) {
        console.log('[STUDENT-09] Profile edit page loaded');
        const formFields = await page.locator('input, select, textarea').count();
        console.log(`[STUDENT-09] Form fields count: ${formFields}`);

        const hasSaveBtn = await checkElementExists(page, 'button[type="submit"], .btn-save, input[type="submit"]');
        console.log(`[STUDENT-09] Save button present: ${hasSaveBtn}`);

        const fieldNames = await page.locator('input[name], select[name]').evaluateAll(el => el.map(e => e.getAttribute('name'))).catch(() => []);
        console.log(`[STUDENT-09] Form field names: ${JSON.stringify(fieldNames)}`);

        if (formFields === 0) {
          bugs.push({
            page: currentUrl,
            role: 'student',
            test: 'STUDENT-09: Profile Edit',
            error: 'Profile edit form has no input fields',
            reproduction: 'Navigate to /profile/edit/ and check for form fields',
            console: [...consoleErrors],
          });
        }
      }

      await takeScreenshot(page, 'STUDENT-09-profile-edit');
      await logPageState(page, 'STUDENT-09-final');

    } catch (e) {
      console.error(`[STUDENT-09] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-09: Profile Edit',
        error: e.message,
        reproduction: 'Navigate to /profile/edit/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-09-fail');
    }
  });

  // ===================================================================
  // STUDENT-10: COURSE ENROLLMENT
  // ===================================================================
  test('STUDENT-10: Course Enrollment - Explore Courses', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-10] Attempting to explore courses');
      await navigateAndWait(page, '/student/explore/');
      await logPageState(page, 'STUDENT-10-explore');

      const currentUrl = page.url();
      console.log(`[STUDENT-10] Explore URL: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[STUDENT-10] Redirected to login - authentication required');
        await takeScreenshot(page, 'STUDENT-10-login-redirect');
      } else if (currentUrl.includes('/explore/') || currentUrl.includes('/student/explore/')) {
        console.log('[STUDENT-10] Explore page loaded');
        const courseCards = await page.locator('.subject-card, .course-card, .card, [class*="course"], [class*="subject"]').count();
        console.log(`[STUDENT-10] Course cards found: ${courseCards}`);

        const enrollButtons = await page.locator('button:has-text("Enroll"), a:has-text("Enroll"), .btn-enroll').count();
        console.log(`[STUDENT-10] Enroll buttons found: ${enrollButtons}`);

        if (enrollButtons > 0) {
          const firstEnroll = page.locator('button:has-text("Enroll"), a:has-text("Enroll"), .btn-enroll').first();
          const enrollBtnText = await firstEnroll.textContent().catch(() => '');
          console.log(`[STUDENT-10] First enroll button: "${enrollBtnText.trim()}"`);

          await tryClick(page, firstEnroll);
          await page.waitForTimeout(2000);
          const postEnrollUrl = page.url();
          console.log(`[STUDENT-10] URL after enroll click: ${postEnrollUrl}`);

          const enrollResult = await page.locator('body').textContent().catch(() => '');
          const hasSuccess = enrollResult.toLowerCase().includes('success') || enrollResult.toLowerCase().includes('enrolled') || enrollResult.toLowerCase().includes('welcome');
          console.log(`[STUDENT-10] Enroll success indicator: ${hasSuccess}`);

          await takeScreenshot(page, 'STUDENT-10-enroll-result');
        } else {
          console.log('[STUDENT-10] No enroll buttons found - may need a published course');
          bugs.push({
            page: currentUrl,
            role: 'student',
            test: 'STUDENT-10: Course Enrollment',
            error: 'No enroll buttons found on explore page (no published courses available?)',
            reproduction: 'Navigate to /student/explore/ and check for enroll buttons',
            console: [...consoleErrors],
          });
        }
      } else {
        console.log(`[STUDENT-10] Unexpected location: ${currentUrl}`);
      }

      await takeScreenshot(page, 'STUDENT-10-explore-final');
      await logPageState(page, 'STUDENT-10-final');

    } catch (e) {
      console.error(`[STUDENT-10] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-10: Course Enrollment',
        error: e.message,
        reproduction: 'Navigate to /student/explore/, try to enroll in a course',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-10-fail');
    }
  });

  // ===================================================================
  // STUDENT-11: COURSE ACCESS (PLAYER)
  // ===================================================================
  test('STUDENT-11: Course Player Access', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-11] Attempting to access course player');
      await navigateAndWait(page, '/course/play/');
      await logPageState(page, 'STUDENT-11-course-player');

      const currentUrl = page.url();
      console.log(`[STUDENT-11] Course player URL: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[STUDENT-11] Redirected to login - authentication required');
      } else {
        const playerContent = await page.locator('body').textContent().catch(() => '');
        const hasPlayer = playerContent.includes('player') || playerContent.includes('video') || playerContent.includes('lesson');
        console.log(`[STUDENT-11] Player content loaded: ${hasPlayer}`);
      }

      await takeScreenshot(page, 'STUDENT-11-player');
      await logPageState(page, 'STUDENT-11-final');

    } catch (e) {
      console.error(`[STUDENT-11] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-11: Course Player',
        error: e.message,
        reproduction: 'Navigate to /course/play/ or /course/<uid>/play/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-11-fail');
    }
  });

  // ===================================================================
  // STUDENT-12: NOTIFICATIONS
  // ===================================================================
  test('STUDENT-12: Notifications Page', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-12] Attempting to access notifications');
      await navigateAndWait(page, '/notifications/');
      await logPageState(page, 'STUDENT-12-notifications');

      const currentUrl = page.url();
      console.log(`[STUDENT-12] Notifications URL: ${currentUrl}`);

      if (currentUrl.includes('/login/')) {
        console.log('[STUDENT-12] Redirected to login - authentication required');
      } else if (currentUrl.includes('/notifications/')) {
        console.log('[STUDENT-12] Notifications page loaded');
        const notifItems = await page.locator('.notif-item, .notification-item, li, .card .item, tr').count();
        console.log(`[STUDENT-12] Notification items count: ${notifItems}`);

        const hasUnread = await checkElementExists(page, '.unread, .notif-item.unread, [class*="unread"]');
        console.log(`[STUDENT-12] Unread notifications present: ${hasUnread}`);
      }

      await takeScreenshot(page, 'STUDENT-12-notifications');
      await logPageState(page, 'STUDENT-12-final');

    } catch (e) {
      console.error(`[STUDENT-12] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-12: Notifications',
        error: e.message,
        reproduction: 'Navigate to /notifications/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-12-fail');
    }
  });

  // ===================================================================
  // STUDENT-13: PERMISSION CHECKS
  // ===================================================================
  test('STUDENT-13: Permission Checks - Blocked URLs', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    const permissionResults = [];

    try {
      // 13a: Teacher dashboard
      console.log('[STUDENT-13a] Accessing /teacher/dashboard/');
      await navigateAndWait(page, '/teacher/dashboard/');
      let url = page.url();
      let blocked = url.includes('/login/') || url.includes('?next=');
      permissionResults.push({ url: '/teacher/dashboard/', blocked, finalUrl: url });
      console.log(`[STUDENT-13a] Teacher dashboard: ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);
      await takeScreenshot(page, 'STUDENT-13a-teacher-dashboard');

      // 13b: Teacher courses
      console.log('[STUDENT-13b] Accessing /teacher/courses/');
      await navigateAndWait(page, '/teacher/courses/');
      url = page.url();
      blocked = url.includes('/login/') || url.includes('?next=');
      permissionResults.push({ url: '/teacher/courses/', blocked, finalUrl: url });
      console.log(`[STUDENT-13b] Teacher courses: ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);

      // 13c: Teacher signup (should be accessible - it's a signup page)
      console.log('[STUDENT-13c] Accessing /teacher/signup/');
      await navigateAndWait(page, '/teacher/signup/');
      url = page.url();
      const isTeacherSignup = url.includes('/teacher/signup/');
      permissionResults.push({ url: '/teacher/signup/', accessible: isTeacherSignup, finalUrl: url });
      console.log(`[STUDENT-13c] Teacher signup: ${isTeacherSignup ? 'ACCESSIBLE' : 'REDIRECTED'} -> ${url}`);

      // 13d: Admin portal
      console.log('[STUDENT-13d] Accessing /customadmin/dashboard/');
      await navigateAndWait(page, '/customadmin/dashboard/');
      url = page.url();
      blocked = url.includes('/portal-secure-access/') || url.includes('/login/') || url.includes('?next=');
      permissionResults.push({ url: '/customadmin/dashboard/', blocked, finalUrl: url });
      console.log(`[STUDENT-13d] Admin dashboard: ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);
      await takeScreenshot(page, 'STUDENT-13d-admin-dashboard');

      // 13e: Admin pending users
      console.log('[STUDENT-13e] Accessing /customadmin/pending/');
      await navigateAndWait(page, '/customadmin/pending/');
      url = page.url();
      blocked = url.includes('/portal-secure-access/') || url.includes('/login/');
      permissionResults.push({ url: '/customadmin/pending/', blocked, finalUrl: url });
      console.log(`[STUDENT-13e] Admin pending: ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);

      // 13f: Admin URL directly
      console.log('[STUDENT-13f] Accessing /customadmin/students/');
      await navigateAndWait(page, '/customadmin/students/');
      url = page.url();
      blocked = url.includes('/portal-secure-access/') || url.includes('/login/');
      permissionResults.push({ url: '/customadmin/students/', blocked, finalUrl: url });
      console.log(`[STUDENT-13f] Admin students: ${blocked ? 'BLOCKED' : 'ALLOWED'} -> ${url}`);

      const allowedEndpoints = permissionResults.filter(r => !r.blocked && r.url !== '/teacher/signup/');
      if (allowedEndpoints.length > 0) {
        console.log(`[STUDENT-13] WARN: ${allowedEndpoints.length} admin/teacher endpoints were NOT blocked`);
        bugs.push({
          page: page.url(),
          role: 'student',
          test: 'STUDENT-13: Permission Checks',
          error: `Student was not blocked from: ${allowedEndpoints.map(e => e.url).join(', ')}`,
          reproduction: 'Try accessing teacher and admin URLs while logged out (or as student)',
          console: [...consoleErrors],
          details: permissionResults,
        });
      } else {
        console.log('[STUDENT-13] SUCCESS: All permission checks passed');
      }

      await takeScreenshot(page, 'STUDENT-13-permissions');
      await logPageState(page, 'STUDENT-13-final');

    } catch (e) {
      console.error(`[STUDENT-13] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-13: Permission Checks',
        error: e.message,
        reproduction: 'Try accessing /teacher/dashboard/, /customadmin/dashboard/, etc.',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-13-fail');
    }
  });

  // ===================================================================
  // STUDENT-14: LOGOUT
  // ===================================================================
  test('STUDENT-14: Logout Flow', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-14] Attempting logout');
      await navigateAndWait(page, '/logout/');
      await page.waitForTimeout(2000);
      await logPageState(page, 'STUDENT-14-logout');

      const currentUrl = page.url();
      console.log(`[STUDENT-14] URL after logout: ${currentUrl}`);

      const redirectedToLogin = currentUrl.includes('/login/') || currentUrl === BASE_URL + '/';
      console.log(`[STUDENT-14] Redirected to login: ${redirectedToLogin}`);

      if (!redirectedToLogin && currentUrl.includes('/logout/')) {
        console.log('[STUDENT-14] Still on logout page, checking for message');
        const logoutMsg = await page.locator('text=logged out, text=logout successful, text=signed out, body').first().textContent().catch(() => '');
        console.log(`[STUDENT-14] Page content: ${logoutMsg.substring(0, 200)}`);
      }

      if (!redirectedToLogin && !currentUrl.includes('/logout/')) {
        bugs.push({
          page: currentUrl,
          role: 'student',
          test: 'STUDENT-14: Logout',
          error: `Logout did not redirect to login page. Ended at: ${currentUrl}`,
          reproduction: 'Navigate to /logout/ and check redirect target',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'STUDENT-14-logout');
      await logPageState(page, 'STUDENT-14-final');

    } catch (e) {
      console.error(`[STUDENT-14] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-14: Logout',
        error: e.message,
        reproduction: 'Navigate to /logout/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-14-fail');
    }
  });

  // ===================================================================
  // STUDENT-15: RESOURCE ACCESS (if applicable)
  // ===================================================================
  test('STUDENT-15: Resource Access Check', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-15] Trying direct resource access patterns');

      await navigateAndWait(page, '/resource/access/');
      let url = page.url();
      console.log(`[STUDENT-15] /resource/access/ -> ${url}`);

      await navigateAndWait(page, '/resource/download/');
      url = page.url();
      console.log(`[STUDENT-15] /resource/download/ -> ${url}`);

      await takeScreenshot(page, 'STUDENT-15-resource-access');
      await logPageState(page, 'STUDENT-15-final');

    } catch (e) {
      console.error(`[STUDENT-15] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-15: Resource Access',
        error: e.message,
        reproduction: 'Access resource URLs without authentication',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-15-fail');
    }
  });

  // ===================================================================
  // STUDENT-16: PASSWORD RECOVERY LINKS CHECK
  // ===================================================================
  test('STUDENT-16: Password Recovery Flow', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[STUDENT-16] Checking password recovery flow');
      await navigateAndWait(page, '/forgot-password/');
      await logPageState(page, 'STUDENT-16-forgot-password');

      const url = page.url();
      console.log(`[STUDENT-16] Forgot password URL: ${url}`);

      const hasForm = await checkElementExists(page, 'form, input, button');
      console.log(`[STUDENT-16] Form present: ${hasForm}`);

      const inputCount = await page.locator('input').count();
      console.log(`[STUDENT-16] Input fields: ${inputCount}`);

      if (url.includes('/login/') && !url.includes('/forgot-password/')) {
        console.log('[STUDENT-16] Redirected to login - might need to access differently');
      }

      await takeScreenshot(page, 'STUDENT-16-forgot-password');
      await logPageState(page, 'STUDENT-16-final');

    } catch (e) {
      console.error(`[STUDENT-16] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'student',
        test: 'STUDENT-16: Password Recovery',
        error: e.message,
        reproduction: 'Navigate to /forgot-password/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'STUDENT-16-fail');
    }
  });

  // ===================================================================
  // BUG REPORT SUMMARY - ALWAYS RUNS LAST
  // ===================================================================
  test('BUG REPORT SUMMARY', () => {
    console.log('========================================');
    console.log('STUDENT FLOW AUDIT COMPLETE');
    console.log('========================================');
    console.log('STUDENT FLOW BUGS FOUND:', bugs.length);
    console.log('========================================');

    if (bugs.length === 0) {
      console.log('  No bugs detected in Student Flow.');
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
    console.log('END OF STUDENT FLOW BUG REPORT');
    console.log('========================================');
  });

});
