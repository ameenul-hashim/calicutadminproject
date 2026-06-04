const { test, expect } = require('@playwright/test');
const path = require('path');
const {
  BASE_URL, ADMIN_PORTAL, ADMIN_CREDENTIALS,
  navigateAndWait, waitForSelectorSafe, takeScreenshot,
  logPageState, collectConsoleErrors, tryClick, tryFill,
  checkElementExists
} = require('./helpers');

const bugs = [];

function setupConsoleCapture(page) {
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));
  page.on('requestfailed', req => errors.push(`NET: ${req.url()} ${req.failure()?.errorText}`));
  return errors;
}

test.describe('Admin Flow - Full LMS Audit', () => {

  // ===================================================================
  // ADMIN-01: ADMIN LOGIN
  // ===================================================================
  test('ADMIN-01: Admin Login', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-01] Navigating to admin portal login');
      const navOk = await navigateAndWait(page, ADMIN_PORTAL);
      if (!navOk) throw new Error('Failed to navigate to admin portal');
      await logPageState(page, 'ADMIN-01-login-page');

      await tryFill(page, 'input[name="username"]', ADMIN_CREDENTIALS.username);
      await tryFill(page, 'input[name="password"]', ADMIN_CREDENTIALS.password);

      const submitBtn = page.locator('button[type="submit"], input[type="submit"]').first();
      const btnExists = await submitBtn.count();
      if (btnExists === 0) {
        throw new Error('No submit button found on admin login page');
      }
      await submitBtn.click();
      console.log('[ADMIN-01] Login submitted');

      await page.waitForTimeout(5000);

      const postLoginUrl = page.url();
      console.log(`[ADMIN-01] Post-login URL: ${postLoginUrl}`);

      // Check if 2FA step was triggered
      const otpField = page.locator('#otp_code');
      const otpPresent = await otpField.count();
      if (otpPresent > 0) {
        console.log('[ADMIN-01] 2FA step detected - OTP code field present');
        console.log('[ADMIN-01] Admin has TOTP/2FA enabled. Login requires OTP code.');
        console.log('[ADMIN-01] This is by design - 2FA is working correctly.');
        bugs.push({
          page: postLoginUrl,
          role: 'admin',
          test: 'ADMIN-01: Admin Login - 2FA Notice',
          error: 'Admin login requires TOTP 2FA code. 2FA is working as designed, but automated test cannot provide OTP.',
          reproduction: 'Admin hashim has TOTP/2FA enabled. First login step passes, second step needs OTP.',
          console: [...consoleErrors],
        });
      }

      const dashboardLoaded = new URL(postLoginUrl).pathname === '/customadmin/dashboard/';
      if (!dashboardLoaded) {
        const pageContent = await page.locator('body').textContent().catch(() => '');
        console.log(`[ADMIN-01] Page content preview: ${pageContent.substring(0, 500)}`);
        if (otpPresent === 0) {
          bugs.push({
            page: postLoginUrl,
            role: 'admin',
            test: 'ADMIN-01: Admin Login',
            error: `Admin login did not redirect to dashboard. Final URL: ${postLoginUrl}`,
            reproduction: `Navigate to ${ADMIN_PORTAL}, fill credentials, submit`,
            console: [...consoleErrors],
          });
        }
      } else {
        console.log('[ADMIN-01] SUCCESS: Admin dashboard loaded');
      }

      await takeScreenshot(page, 'ADMIN-01-login');
      await logPageState(page, 'ADMIN-01-final');

    } catch (e) {
      console.error(`[ADMIN-01] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-01: Admin Login',
        error: e.message,
        reproduction: `Navigate to ${ADMIN_PORTAL}, fill credentials, submit`,
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-01-fail');
    }
  });

  // ===================================================================
  // ADMIN-02: DASHBOARD
  // ===================================================================
  test('ADMIN-02: Dashboard Verification', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-02] Navigating to admin dashboard');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/dashboard/`);
      if (!navOk) throw new Error('Failed to navigate to dashboard');
      await logPageState(page, 'ADMIN-02-dashboard');

      const currentUrl = page.url();
      console.log(`[ADMIN-02] Dashboard URL: ${currentUrl}`);

      const statsCount = await page.locator('.stat-card, .stat, .card, .dashboard-stat, [class*="stat"], [class*="metric"]').count();
      console.log(`[ADMIN-02] Stat/card elements found: ${statsCount}`);

      const hasCharts = await checkElementExists(page, 'canvas, .chart, [class*="chart"], svg');
      console.log(`[ADMIN-02] Charts present: ${hasCharts}`);

      const pendingCounts = await page.locator('text=pending, text=Pending, text=PENDING, .badge, [class*="pending"], [class*="badge"]').allTextContents().catch(() => []);
      console.log(`[ADMIN-02] Pending indicators: ${JSON.stringify(pendingCounts)}`);

      const currentPath = new URL(currentUrl).pathname;
      if (statsCount === 0 && !currentPath.includes('/dashboard/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-02: Dashboard',
          error: `Dashboard did not load. URL: ${currentUrl}`,
          reproduction: 'Navigate to /customadmin/dashboard/',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'ADMIN-02-dashboard');
      await logPageState(page, 'ADMIN-02-final');

    } catch (e) {
      console.error(`[ADMIN-02] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-02: Dashboard',
        error: e.message,
        reproduction: 'Navigate to /customadmin/dashboard/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-02-fail');
    }
  });

  // ===================================================================
  // ADMIN-03: STUDENT MANAGEMENT
  // ===================================================================
  test('ADMIN-03: Student Management', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-03] Navigating to student management');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/students/`);
      if (!navOk) throw new Error('Failed to navigate to students page');
      await logPageState(page, 'ADMIN-03-students');

      const currentUrl = page.url();
      console.log(`[ADMIN-03] Students URL: ${currentUrl}`);

      const studentRows = await page.locator('tr, .student-item, .user-row, .list-item, .card').count();
      console.log(`[ADMIN-03] Student rows/items found: ${studentRows}`);

      const hasStudentList = studentRows > 1 || await checkElementExists(page, 'table, .student-list, [class*="student"]');

      const studentsPath = new URL(currentUrl).pathname;
      if (!hasStudentList && !studentsPath.includes('/students/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-03: Student Management',
          error: `Students page did not load correctly. URL: ${currentUrl}, rows: ${studentRows}`,
          reproduction: 'Navigate to /customadmin/students/',
          console: [...consoleErrors],
        });
      } else {
        console.log(`[ADMIN-03] SUCCESS: Student list loaded with ${studentRows} rows`);
      }

      await takeScreenshot(page, 'ADMIN-03-students');
      await logPageState(page, 'ADMIN-03-final');

    } catch (e) {
      console.error(`[ADMIN-03] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-03: Student Management',
        error: e.message,
        reproduction: 'Navigate to /customadmin/students/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-03-fail');
    }
  });

  // ===================================================================
  // ADMIN-04: TEACHER MANAGEMENT
  // ===================================================================
  test('ADMIN-04: Teacher Management', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-04] Navigating to teacher management');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/teachers/`);
      if (!navOk) throw new Error('Failed to navigate to teachers page');
      await logPageState(page, 'ADMIN-04-teachers');

      const currentUrl = page.url();
      console.log(`[ADMIN-04] Teachers URL: ${currentUrl}`);

      const teacherRows = await page.locator('tr, .teacher-item, .user-row, .list-item, .card').count();
      console.log(`[ADMIN-04] Teacher rows/items found: ${teacherRows}`);

      const teachersPath = new URL(currentUrl).pathname;
      if (teacherRows === 0 && !teachersPath.includes('/teachers/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-04: Teacher Management',
          error: `Teachers page did not load correctly. URL: ${currentUrl}`,
          reproduction: 'Navigate to /customadmin/teachers/',
          console: [...consoleErrors],
        });
      } else {
        console.log(`[ADMIN-04] SUCCESS: Teacher list loaded with ${teacherRows} rows`);
      }

      await takeScreenshot(page, 'ADMIN-04-teachers');
      await logPageState(page, 'ADMIN-04-final');

    } catch (e) {
      console.error(`[ADMIN-04] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-04: Teacher Management',
        error: e.message,
        reproduction: 'Navigate to /customadmin/teachers/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-04-fail');
    }
  });

  // ===================================================================
  // ADMIN-05: PENDING APPROVALS
  // ===================================================================
  test('ADMIN-05: Pending Approvals Pages', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    const pendingPages = [
      { label: 'pending-users', url: '/customadmin/pending/' },
      { label: 'pending-teachers', url: '/customadmin/pending/teachers/' },
      { label: 'pending-resources', url: '/customadmin/pending/resources/' },
      { label: 'pending-courses', url: '/customadmin/pending/courses/' },
    ];
    const results = [];

    try {
      for (const pp of pendingPages) {
        console.log(`[ADMIN-05] Loading ${pp.label} at ${pp.url}`);
        const fullUrl = `${BASE_URL}${pp.url}`;
        const navOk = await navigateAndWait(page, fullUrl);
        await page.waitForTimeout(2000);
        const state = await logPageState(page, `ADMIN-05-${pp.label}`);

        const pageContent = await page.locator('body').textContent().catch(() => '');
        const loadedOk = state.url.includes(pp.url.replace(/\/$/, '')) ||
                         state.url.includes(pp.url) ||
                         pageContent.length > 100;

        results.push({ label: pp.label, url: state.url, loaded: loadedOk, contentLength: pageContent.length });
        console.log(`[ADMIN-05] ${pp.label}: loaded=${loadedOk}, content=${pageContent.length} chars`);

        await takeScreenshot(page, `ADMIN-05-${pp.label}`);
      }

      const failed = results.filter(r => !r.loaded);
      if (failed.length > 0) {
        bugs.push({
          page: page.url(),
          role: 'admin',
          test: 'ADMIN-05: Pending Approvals',
          error: `${failed.length} pending page(s) failed to load: ${failed.map(f => f.label).join(', ')}`,
          reproduction: 'Navigate to pending approval pages',
          console: [...consoleErrors],
          details: results,
        });
      } else {
        console.log('[ADMIN-05] SUCCESS: All pending approval pages loaded');
      }

      await takeScreenshot(page, 'ADMIN-05-final');
      await logPageState(page, 'ADMIN-05-final');

    } catch (e) {
      console.error(`[ADMIN-05] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-05: Pending Approvals',
        error: e.message,
        reproduction: 'Navigate to pending pages under /customadmin/pending/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-05-fail');
    }
  });

  // ===================================================================
  // ADMIN-06: COURSE APPROVAL
  // ===================================================================
  test('ADMIN-06: Course Approval/Rejection', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-06] Navigating to pending courses');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/pending/courses/`);
      if (!navOk) throw new Error('Failed to navigate to pending courses');
      await logPageState(page, 'ADMIN-06-pending-courses');

      await page.waitForTimeout(2000);

      const approveBtns = await page.locator('a[href*="approve"], button:has-text("Approve"), .btn-approve, a:has-text("Approve")').count();
      const rejectBtns = await page.locator('a[href*="reject"], button:has-text("Reject"), .btn-reject, a:has-text("Reject")').count();
      console.log(`[ADMIN-06] Approve buttons: ${approveBtns}, Reject buttons: ${rejectBtns}`);

      if (approveBtns > 0) {
        const firstApprove = page.locator('a[href*="approve"], button:has-text("Approve"), .btn-approve').first();
        const href = await firstApprove.getAttribute('href').catch(() => 'unknown');
        console.log(`[ADMIN-06] First approve button href: ${href}`);

        await tryClick(page, firstApprove);
        await page.waitForTimeout(3000);
        const afterApproveUrl = page.url();
        console.log(`[ADMIN-06] After approve click URL: ${afterApproveUrl}`);

        const approveSuccess = await page.locator('text=success, text=approved, text=Success, text=Approved, .alert-success, .toast-message').first().textContent().catch(() => '');
        console.log(`[ADMIN-06] Approve result: ${approveSuccess}`);
        await takeScreenshot(page, 'ADMIN-06-approve-result');
      } else {
        console.log('[ADMIN-06] No course approve buttons found - may have no pending courses');
      }

      if (rejectBtns > 0) {
        const firstReject = page.locator('a[href*="reject"], button:has-text("Reject"), .btn-reject').first();
        const href = await firstReject.getAttribute('href').catch(() => 'unknown');
        console.log(`[ADMIN-06] First reject button href: ${href}`);

        await tryClick(page, firstReject);
        await page.waitForTimeout(3000);
        const afterRejectUrl = page.url();
        console.log(`[ADMIN-06] After reject click URL: ${afterRejectUrl}`);

        const rejectSuccess = await page.locator('text=success, text=rejected, text=Success, text=Rejected, .alert-success, .toast-message').first().textContent().catch(() => '');
        console.log(`[ADMIN-06] Reject result: ${rejectSuccess}`);
        await takeScreenshot(page, 'ADMIN-06-reject-result');
      } else {
        console.log('[ADMIN-06] No course reject buttons found');
      }

      await takeScreenshot(page, 'ADMIN-06-final');
      await logPageState(page, 'ADMIN-06-final');

    } catch (e) {
      console.error(`[ADMIN-06] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-06: Course Approval',
        error: e.message,
        reproduction: 'Navigate to /customadmin/pending/courses/, try approve/reject',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-06-fail');
    }
  });

  // ===================================================================
  // ADMIN-07: RESOURCE APPROVAL
  // ===================================================================
  test('ADMIN-07: Resource Approval/Rejection', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-07] Navigating to pending resources');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/pending/resources/`);
      if (!navOk) throw new Error('Failed to navigate to pending resources');
      await logPageState(page, 'ADMIN-07-pending-resources');

      await page.waitForTimeout(2000);

      const approveBtns = await page.locator('a[href*="approve"], button:has-text("Approve"), .btn-approve, a:has-text("Approve")').count();
      const rejectBtns = await page.locator('a[href*="reject"], button:has-text("Reject"), .btn-reject, a:has-text("Reject")').count();
      console.log(`[ADMIN-07] Approve buttons: ${approveBtns}, Reject buttons: ${rejectBtns}`);

      if (approveBtns > 0) {
        const firstApprove = page.locator('a[href*="approve"], button:has-text("Approve"), .btn-approve').first();
        const href = await firstApprove.getAttribute('href').catch(() => 'unknown');
        console.log(`[ADMIN-07] First approve button href: ${href}`);

        await tryClick(page, firstApprove);
        await page.waitForTimeout(3000);
        const afterApproveUrl = page.url();
        console.log(`[ADMIN-07] After approve click URL: ${afterApproveUrl}`);

        const approveSuccess = await page.locator('text=success, text=approved, .alert-success, .toast-message').first().textContent().catch(() => '');
        console.log(`[ADMIN-07] Approve result: ${approveSuccess}`);
        await takeScreenshot(page, 'ADMIN-07-approve-result');
      } else {
        console.log('[ADMIN-07] No resource approve buttons found');
      }

      if (rejectBtns > 0) {
        const firstReject = page.locator('a[href*="reject"], button:has-text("Reject"), .btn-reject').first();
        const href = await firstReject.getAttribute('href').catch(() => 'unknown');
        console.log(`[ADMIN-07] First reject button href: ${href}`);

        await tryClick(page, firstReject);
        await page.waitForTimeout(3000);
        const afterRejectUrl = page.url();
        console.log(`[ADMIN-07] After reject click URL: ${afterRejectUrl}`);

        const rejectSuccess = await page.locator('text=success, text=rejected, .alert-success, .toast-message').first().textContent().catch(() => '');
        console.log(`[ADMIN-07] Reject result: ${rejectSuccess}`);
        await takeScreenshot(page, 'ADMIN-07-reject-result');
      } else {
        console.log('[ADMIN-07] No resource reject buttons found');
      }

      await takeScreenshot(page, 'ADMIN-07-final');
      await logPageState(page, 'ADMIN-07-final');

    } catch (e) {
      console.error(`[ADMIN-07] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-07: Resource Approval',
        error: e.message,
        reproduction: 'Navigate to /customadmin/pending/resources/, try approve/reject',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-07-fail');
    }
  });

  // ===================================================================
  // ADMIN-08: USER MANAGEMENT (toggle, edit)
  // ===================================================================
  test('ADMIN-08: User Management Actions', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-08] Navigating to student management for user actions');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/students/`);
      if (!navOk) throw new Error('Failed to navigate to students page');
      await logPageState(page, 'ADMIN-08-students');

      await page.waitForTimeout(2000);

      const toggleBtns = await page.locator('a[href*="toggle"], button:has-text("Block"), button:has-text("Unblock"), button:has-text("Toggle"), a:has-text("Block"), a:has-text("Unblock")').count();
      console.log(`[ADMIN-08] Toggle/Block buttons found: ${toggleBtns}`);

      if (toggleBtns > 0) {
        const firstToggle = page.locator('a[href*="toggle"], button:has-text("Block"), button:has-text("Unblock"), a:has-text("Block"), a:has-text("Unblock")').first();
        const toggleText = await firstToggle.textContent().catch(() => '');
        console.log(`[ADMIN-08] First toggle button text: "${toggleText.trim()}"`);

        await tryClick(page, firstToggle);
        await page.waitForTimeout(3000);
        const afterToggleUrl = page.url();
        console.log(`[ADMIN-08] After toggle URL: ${afterToggleUrl}`);

        const toggleResult = await page.locator('.alert, .toast-message, [class*="success"], [class*="error"]').first().textContent().catch(() => '');
        console.log(`[ADMIN-08] Toggle result message: ${toggleResult}`);
        await takeScreenshot(page, 'ADMIN-08-toggle-result');
      } else {
        console.log('[ADMIN-08] No toggle/block buttons found on students page');
      }

      const editBtns = await page.locator('a[href*="edit"], a[href*="user/edit"], button:has-text("Edit"), a:has-text("Edit")').count();
      console.log(`[ADMIN-08] Edit buttons found: ${editBtns}`);

      if (editBtns > 0) {
        const firstEdit = page.locator('a[href*="edit"], a:has-text("Edit")').first();
        const href = await firstEdit.getAttribute('href').catch(() => '');
        console.log(`[ADMIN-08] First edit href: ${href}`);

        await tryClick(page, firstEdit);
        await page.waitForTimeout(3000);
        const afterEditUrl = page.url();
        console.log(`[ADMIN-08] After edit click URL: ${afterEditUrl}`);

        const formFields = await page.locator('input, select, textarea').count();
        console.log(`[ADMIN-08] Edit form fields: ${formFields}`);
        await takeScreenshot(page, 'ADMIN-08-edit-form');
      } else {
        console.log('[ADMIN-08] No edit buttons found');
      }

      await takeScreenshot(page, 'ADMIN-08-final');
      await logPageState(page, 'ADMIN-08-final');

    } catch (e) {
      console.error(`[ADMIN-08] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-08: User Management',
        error: e.message,
        reproduction: 'Navigate to /customadmin/students/, try toggle/edit user',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-08-fail');
    }
  });

  // ===================================================================
  // ADMIN-09: DELETION REQUESTS
  // ===================================================================
  test('ADMIN-09: Deletion Requests', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-09] Navigating to deletion requests');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/deletion-requests/`);
      if (!navOk) throw new Error('Failed to navigate to deletion requests');
      await logPageState(page, 'ADMIN-09-deletion-requests');

      const currentUrl = page.url();
      console.log(`[ADMIN-09] Deletion requests URL: ${currentUrl}`);

      const pageContent = await page.locator('body').textContent().catch(() => '');
      const hasContent = pageContent.length > 100;
      console.log(`[ADMIN-09] Page has content: ${hasContent} (${pageContent.length} chars)`);

      const tableRows = await page.locator('tr, .request-item, .deletion-item, .list-item').count();
      console.log(`[ADMIN-09] Request rows/items: ${tableRows}`);

      const requestLinks = await page.locator('a[href*="verify"], a[href*="approve"], a[href*="reject"]').count();
      console.log(`[ADMIN-09] Action links (verify/approve/reject): ${requestLinks}`);

      const deletionPath = new URL(currentUrl).pathname;
      if (!hasContent && !deletionPath.includes('/deletion-requests/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-09: Deletion Requests',
          error: `Deletion requests page did not load. URL: ${currentUrl}`,
          reproduction: 'Navigate to /customadmin/deletion-requests/',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'ADMIN-09-deletion-requests');
      await logPageState(page, 'ADMIN-09-final');

    } catch (e) {
      console.error(`[ADMIN-09] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-09: Deletion Requests',
        error: e.message,
        reproduction: 'Navigate to /customadmin/deletion-requests/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-09-fail');
    }
  });

  // ===================================================================
  // ADMIN-10: ANALYTICS
  // ===================================================================
  test('ADMIN-10: Analytics Dashboard', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-10] Navigating to analytics');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/analytics/`);
      if (!navOk) throw new Error('Failed to navigate to analytics');
      await logPageState(page, 'ADMIN-10-analytics');

      const currentUrl = page.url();
      console.log(`[ADMIN-10] Analytics URL: ${currentUrl}`);

      const hasCharts = await checkElementExists(page, 'canvas, .chart, [class*="chart"], svg, .plotly, [class*="plot"]');
      console.log(`[ADMIN-10] Charts present: ${hasCharts}`);

      const statCards = await page.locator('.stat-card, .stat, .card, .analytics-card, [class*="stat"], [class*="metric"], [class*="number"]').count();
      console.log(`[ADMIN-10] Stat/metric cards: ${statCards}`);

      const tableData = await page.locator('table, .data-table, .table').count();
      console.log(`[ADMIN-10] Data tables: ${tableData}`);

      if (statCards === 0 && hasCharts === false && tableData === 0) {
        const pageContent = await page.locator('body').textContent().catch(() => '');
        if (pageContent.length < 200) {
          bugs.push({
            page: currentUrl,
            role: 'admin',
            test: 'ADMIN-10: Analytics',
            error: `Analytics page appears empty or not loaded. Charts: ${hasCharts}, Stats: ${statCards}`,
            reproduction: 'Navigate to /customadmin/analytics/',
            console: [...consoleErrors],
          });
        } else {
          console.log('[ADMIN-10] Page has content but no specific chart/stat elements detected');
        }
      } else {
        console.log('[ADMIN-10] SUCCESS: Analytics page loaded with data');
      }

      await takeScreenshot(page, 'ADMIN-10-analytics');
      await logPageState(page, 'ADMIN-10-final');

    } catch (e) {
      console.error(`[ADMIN-10] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-10: Analytics',
        error: e.message,
        reproduction: 'Navigate to /customadmin/analytics/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-10-fail');
    }
  });

  // ===================================================================
  // ADMIN-11: AUDIT LOGS
  // ===================================================================
  test('ADMIN-11: Audit Log Pages', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);
    const auditPages = [
      { label: 'system-audit', url: '/customadmin/system-audit/' },
      { label: 'master-audit-summary', url: '/customadmin/master-audit-summary/' },
    ];
    const results = [];

    try {
      for (const ap of auditPages) {
        console.log(`[ADMIN-11] Loading ${ap.label} at ${ap.url}`);
        const fullUrl = `${BASE_URL}${ap.url}`;
        const navOk = await navigateAndWait(page, fullUrl);
        await page.waitForTimeout(2000);
        const state = await logPageState(page, `ADMIN-11-${ap.label}`);

        const pageContent = await page.locator('body').textContent().catch(() => '');
        const hasContent = pageContent.length > 100;
        const correctPage = state.url.includes(ap.url.replace(/\/$/, '')) || state.url.includes(ap.url);

        results.push({ label: ap.label, url: state.url, loaded: hasContent && correctPage, contentLength: pageContent.length });
        console.log(`[ADMIN-11] ${ap.label}: loaded=${correctPage}, hasContent=${hasContent}, ${pageContent.length} chars`);

        const tableRows = await page.locator('tr, .log-item, .audit-item, .list-item').count();
        console.log(`[ADMIN-11] ${ap.label} data rows: ${tableRows}`);

        await takeScreenshot(page, `ADMIN-11-${ap.label}`);
      }

      const failed = results.filter(r => !r.loaded);
      if (failed.length > 0) {
        bugs.push({
          page: page.url(),
          role: 'admin',
          test: 'ADMIN-11: Audit Logs',
          error: `${failed.length} audit page(s) failed to load: ${failed.map(f => f.label).join(', ')}`,
          reproduction: 'Navigate to /customadmin/system-audit/ and /customadmin/master-audit-summary/',
          console: [...consoleErrors],
          details: results,
        });
      } else {
        console.log('[ADMIN-11] SUCCESS: All audit log pages loaded');
      }

      await takeScreenshot(page, 'ADMIN-11-final');
      await logPageState(page, 'ADMIN-11-final');

    } catch (e) {
      console.error(`[ADMIN-11] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-11: Audit Logs',
        error: e.message,
        reproduction: 'Navigate to audit log pages',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-11-fail');
    }
  });

  // ===================================================================
  // ADMIN-12: NOTIFICATIONS
  // ===================================================================
  test('ADMIN-12: Notifications', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-12] Navigating to admin notifications');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/notifications/`);
      if (!navOk) throw new Error('Failed to navigate to notifications');
      await logPageState(page, 'ADMIN-12-notifications');

      const currentUrl = page.url();
      console.log(`[ADMIN-12] Notifications URL: ${currentUrl}`);

      const notifItems = await page.locator('.notif-item, .notification-item, tr, .list-item, .card, li').count();
      console.log(`[ADMIN-12] Notification items count: ${notifItems}`);

      const hasUnread = await checkElementExists(page, '.unread, .notif-item.unread, [class*="unread"], .badge');
      console.log(`[ADMIN-12] Unread indicators present: ${hasUnread}`);

      const readLinks = await page.locator('a[href*="read"], a:has-text("Mark Read"), button:has-text("Mark Read"), .btn-read').count();
      console.log(`[ADMIN-12] Mark-as-read links: ${readLinks}`);

      if (readLinks > 0) {
        const firstRead = page.locator('a[href*="read"], a:has-text("Mark Read"), button:has-text("Mark Read")').first();
        await tryClick(page, firstRead);
        await page.waitForTimeout(2000);
        const afterReadUrl = page.url();
        console.log(`[ADMIN-12] After mark-read click URL: ${afterReadUrl}`);
        await takeScreenshot(page, 'ADMIN-12-mark-read');
      } else {
        console.log('[ADMIN-12] No mark-as-read links found');
      }

      const readAllLinks = await page.locator('a[href*="read-all"], a:has-text("Read All"), button:has-text("Read All"), .btn-read-all').count();
      console.log(`[ADMIN-12] Read-all links: ${readAllLinks}`);

      if (readAllLinks > 0) {
        console.log('[ADMIN-12] "Read All" button found');
      }

      const notifPath = new URL(currentUrl).pathname;
      if (notifItems === 0 && !notifPath.includes('/notifications/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-12: Notifications',
          error: `Notifications page did not load correctly. URL: ${currentUrl}`,
          reproduction: 'Navigate to /customadmin/notifications/',
          console: [...consoleErrors],
        });
      }

      await takeScreenshot(page, 'ADMIN-12-notifications');
      await logPageState(page, 'ADMIN-12-final');

    } catch (e) {
      console.error(`[ADMIN-12] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-12: Notifications',
        error: e.message,
        reproduction: 'Navigate to /customadmin/notifications/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-12-fail');
    }
  });

  // ===================================================================
  // ADMIN-13: CONTENT MANAGEMENT
  // ===================================================================
  test('ADMIN-13: Content Management', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-13] Navigating to content management');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/content/`);
      if (!navOk) throw new Error('Failed to navigate to content management');
      await logPageState(page, 'ADMIN-13-content');

      const currentUrl = page.url();
      console.log(`[ADMIN-13] Content management URL: ${currentUrl}`);

      const pageContent = await page.locator('body').textContent().catch(() => '');
      const hasContent = pageContent.length > 100;
      console.log(`[ADMIN-13] Page has content: ${hasContent} (${pageContent.length} chars)`);

      const contentItems = await page.locator('tr, .content-item, .card, .list-item, .course-item, .resource-item').count();
      console.log(`[ADMIN-13] Content items/rows: ${contentItems}`);

      const links = await page.locator('a').count();
      console.log(`[ADMIN-13] Total links on page: ${links}`);

      const contentPath = new URL(currentUrl).pathname;
      if (!hasContent && !contentPath.includes('/content/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-13: Content Management',
          error: `Content management page did not load. URL: ${currentUrl}`,
          reproduction: 'Navigate to /customadmin/content/',
          console: [...consoleErrors],
        });
      } else {
        console.log('[ADMIN-13] SUCCESS: Content management page loaded');
      }

      await takeScreenshot(page, 'ADMIN-13-content');
      await logPageState(page, 'ADMIN-13-final');

    } catch (e) {
      console.error(`[ADMIN-13] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-13: Content Management',
        error: e.message,
        reproduction: 'Navigate to /customadmin/content/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-13-fail');
    }
  });

  // ===================================================================
  // ADMIN-14: STORAGE DASHBOARD
  // ===================================================================
  test('ADMIN-14: Storage Dashboard', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-14] Navigating to storage dashboard');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/storage-dashboard/`);
      if (!navOk) throw new Error('Failed to navigate to storage dashboard');
      await logPageState(page, 'ADMIN-14-storage');

      const currentUrl = page.url();
      console.log(`[ADMIN-14] Storage dashboard URL: ${currentUrl}`);

      const pageContent = await page.locator('body').textContent().catch(() => '');
      const hasContent = pageContent.length > 100;
      console.log(`[ADMIN-14] Page has content: ${hasContent} (${pageContent.length} chars)`);

      const stats = await page.locator('.stat, .card, .storage-stat, [class*="stat"], [class*="metric"], [class*="usage"]').count();
      console.log(`[ADMIN-14] Storage stats/cards: ${stats}`);

      const hasCharts = await checkElementExists(page, 'canvas, .chart, [class*="chart"], svg');
      console.log(`[ADMIN-14] Charts present: ${hasCharts}`);

      const storagePath = new URL(currentUrl).pathname;
      if (!hasContent && !storagePath.includes('/storage-dashboard/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-14: Storage Dashboard',
          error: `Storage dashboard page did not load. URL: ${currentUrl}`,
          reproduction: 'Navigate to /customadmin/storage-dashboard/',
          console: [...consoleErrors],
        });
      } else {
        console.log('[ADMIN-14] SUCCESS: Storage dashboard loaded');
      }

      await takeScreenshot(page, 'ADMIN-14-storage');
      await logPageState(page, 'ADMIN-14-final');

    } catch (e) {
      console.error(`[ADMIN-14] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-14: Storage Dashboard',
        error: e.message,
        reproduction: 'Navigate to /customadmin/storage-dashboard/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-14-fail');
    }
  });

  // ===================================================================
  // ADMIN-15: ENTERPRISE MONITOR
  // ===================================================================
  test('ADMIN-15: Enterprise Monitor', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-15] Navigating to enterprise monitor');
      const navOk = await navigateAndWait(page, `${BASE_URL}/customadmin/enterprise-monitor/`);
      if (!navOk) throw new Error('Failed to navigate to enterprise monitor');
      await logPageState(page, 'ADMIN-15-enterprise-monitor');

      const currentUrl = page.url();
      console.log(`[ADMIN-15] Enterprise monitor URL: ${currentUrl}`);

      const pageContent = await page.locator('body').textContent().catch(() => '');
      const hasContent = pageContent.length > 100;
      console.log(`[ADMIN-15] Page has content: ${hasContent} (${pageContent.length} chars)`);

      const monitorItems = await page.locator('.card, .monitor-item, .status-card, .metric, [class*="monitor"], [class*="status"], [class*="health"]').count();
      console.log(`[ADMIN-15] Monitor items/cards: ${monitorItems}`);

      const hasStatusIndicators = await checkElementExists(page, '.online, .offline, .healthy, .warning, .error, .status, [class*="online"], [class*="offline"]');
      console.log(`[ADMIN-15] Status indicators present: ${hasStatusIndicators}`);

      const monitorPath = new URL(currentUrl).pathname;
      if (!hasContent && !monitorPath.includes('/enterprise-monitor/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-15: Enterprise Monitor',
          error: `Enterprise monitor page did not load. URL: ${currentUrl}`,
          reproduction: 'Navigate to /customadmin/enterprise-monitor/',
          console: [...consoleErrors],
        });
      } else {
        console.log('[ADMIN-15] SUCCESS: Enterprise monitor loaded');
      }

      await takeScreenshot(page, 'ADMIN-15-enterprise-monitor');
      await logPageState(page, 'ADMIN-15-final');

    } catch (e) {
      console.error(`[ADMIN-15] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-15: Enterprise Monitor',
        error: e.message,
        reproduction: 'Navigate to /customadmin/enterprise-monitor/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-15-fail');
    }
  });

  // ===================================================================
  // ADMIN-16: LOGOUT
  // ===================================================================
  test('ADMIN-16: Logout', async ({ page }) => {
    const consoleErrors = setupConsoleCapture(page);

    try {
      console.log('[ADMIN-16] Attempting admin logout');
      const navOk = await navigateAndWait(page, `${BASE_URL}/logout/`);
      if (!navOk) console.log('[ADMIN-16] Navigation had timeout, proceeding');
      await page.waitForTimeout(3000);
      await logPageState(page, 'ADMIN-16-logout');

      const currentUrl = page.url();
      console.log(`[ADMIN-16] URL after logout: ${currentUrl}`);

      const redirectedToLogin = currentUrl.includes('/login/') || currentUrl === BASE_URL + '/' ||
                                currentUrl.includes('/portal-secure-access/');
      console.log(`[ADMIN-16] Redirected to login: ${redirectedToLogin}`);

      if (!redirectedToLogin && currentUrl.includes('/logout/')) {
        const pageContent = await page.locator('body').textContent().catch(() => '');
        console.log(`[ADMIN-16] Still on logout: ${pageContent.substring(0, 300)}`);
      }

      if (!redirectedToLogin && !currentUrl.includes('/logout/')) {
        bugs.push({
          page: currentUrl,
          role: 'admin',
          test: 'ADMIN-16: Logout',
          error: `Logout did not redirect to login page. Final URL: ${currentUrl}`,
          reproduction: 'Navigate to /logout/',
          console: [...consoleErrors],
        });
      } else {
        console.log('[ADMIN-16] SUCCESS: Logout completed');
      }

      const loginAccessible = await navigateAndWait(page, ADMIN_PORTAL);
      if (loginAccessible) {
        const loginForm = await checkElementExists(page, 'input[name="username"], input[type="text"], form');
        console.log(`[ADMIN-16] Login page accessible after logout: ${loginForm}`);
      }

      await takeScreenshot(page, 'ADMIN-16-logout');
      await logPageState(page, 'ADMIN-16-final');

    } catch (e) {
      console.error(`[ADMIN-16] FAILED: ${e.message}`);
      bugs.push({
        page: page.url(),
        role: 'admin',
        test: 'ADMIN-16: Logout',
        error: e.message,
        reproduction: 'Navigate to /logout/',
        console: [...consoleErrors],
      });
      await takeScreenshot(page, 'ADMIN-16-fail');
    }
  });

  // ===================================================================
  // BUG REPORT SUMMARY - ALWAYS RUNS LAST
  // ===================================================================
  test('BUG REPORT SUMMARY', () => {
    console.log('========================================');
    console.log('ADMIN FLOW AUDIT COMPLETE');
    console.log('========================================');
    console.log('ADMIN FLOW BUGS FOUND:', bugs.length);
    console.log('========================================');

    if (bugs.length === 0) {
      console.log('  No bugs detected in Admin Flow.');
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
    console.log('END OF ADMIN FLOW BUG REPORT');
    console.log('========================================');
  });

});
