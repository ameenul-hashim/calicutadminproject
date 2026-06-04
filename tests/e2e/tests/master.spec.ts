import { test, expect } from '../helpers/test-utils';
import path from 'path';

test.describe('NeoLearn LMS Master Audit', () => {
  
  test('LMS Workflow: Instrumented Audit', async ({ page, context }) => {
    const timestamp = Date.now();
    const testData = {
      teacher: {
        username: `teacher_${timestamp}`,
        fullname: `Teacher ${timestamp}`,
        email: `teacher_${timestamp}@example.com`,
        phone: `9${timestamp.toString().slice(-9)}`,
        password: 'StrongPassword123!'
      },
      student: {
        username: `student_${timestamp}`,
        fullname: `Student ${timestamp}`,
        email: `student_${timestamp}@example.com`,
        phone: `8${timestamp.toString().slice(-9)}`,
        password: 'StrongPassword123!'
      },
      admin: {
        username: 'hashim',
        password: 'Pkd02786*'
      },
      course: {
        title: `Master Course ${timestamp}`,
        description: 'Comprehensive E2E Verification Course Content.',
        chapter: 'Introduction to E2E'
      }
    };

    const LOG_STEP = async (stepNumber: number, message: string) => {
      const url = page.url();
      const title = await page.title().catch(() => 'N/A');
      console.log(`\n===== [STEP ${stepNumber}] =====`);
      console.log(`STAGE: ${message}`);
      console.log(`URL: ${url}`);
      console.log(`TITLE: ${title}`);
      await page.screenshot({ path: `screenshots/audit_step_${stepNumber}_${message.replace(/\s+/g, '_').toLowerCase()}.png`, fullPage: true });
    };

    // Install URL tracking
    const visitedURLs: string[] = [];
    page.on('framenavigated', async (frame) => {
      if (frame === page.mainFrame()) {
        visitedURLs.push(frame.url());
        console.log(`[NAV] -> ${frame.url()}`);
      }
    });

    test.setTimeout(400000);

    try {
      // ============================================================
      // PHASE 1: STUDENT SIGNUP
      // ============================================================
      await LOG_STEP(1, 'Student Signup Started');
      await page.goto('/signup/');
      await LOG_STEP(2, 'Student Signup Page Loaded');
      
      await page.fill('#username', testData.student.username);
      await page.fill('#fullname', testData.student.fullname);
      await page.fill('#email', testData.student.email);
      await page.fill('#phone_number', testData.student.phone);
      
      const fileChooserPromise = page.waitForEvent('filechooser');
      await page.click('#upload-label');
      const fileChooser = await fileChooserPromise;
      await fileChooser.setFiles(path.join(process.cwd(), 'test_resource.pdf'));
      console.log('[INFO] Student PDF file chosen');

      await page.fill('#password', testData.student.password);
      await page.fill('#confirm_password', testData.student.password);
      
      // Capture all server toast messages before clicking
      const consoleErrors: string[] = [];
      page.on('console', msg => {
        if (msg.type() === 'error') consoleErrors.push(msg.text());
      });

      await page.click('#signup-btn');
      await LOG_STEP(3, 'Student Signup Submitted');
      
      // Wait for processing spinner to disappear
      try {
        await expect(page.locator('button:has-text("Processing")')).not.toBeVisible({ timeout: 90000 });
      } catch (_) {}
      
      await LOG_STEP(4, 'Student Signup Processing Done');

      // Check if still on signup — log error
      if (page.url().includes('/signup/')) {
        const pageContent = await page.content();
        const messages = await page.locator('.alert, .toast-message, .error-msg, [class*="error"], [class*="alert"]').allTextContents();
        console.log('[SIGNUP ERROR] Still on signup page. Messages:', JSON.stringify(messages));
        const toasts = await page.locator('.toast-message').allTextContents();
        console.log('[SIGNUP TOAST]', JSON.stringify(toasts));
        throw new Error(`[BLOCKER] Student Signup failed — still on signup page. Messages: ${JSON.stringify(messages)}`);
      }

      // Should be on /login/
      await expect(page).toHaveURL(/login/, { timeout: 30000 });
      await LOG_STEP(5, 'Student Signup SUCCESS — Redirected to Login');

      // ============================================================
      // PHASE 2: TEACHER SIGNUP
      // ============================================================
      await LOG_STEP(6, 'Teacher Signup Started');
      await page.goto('/teacher/signup/');
      await LOG_STEP(7, 'Teacher Signup Page Loaded');
      
      await page.fill('#username', testData.teacher.username);
      await page.fill('#fullname', testData.teacher.fullname);
      await page.fill('#email', testData.teacher.email);
      await page.fill('#phone_number', testData.teacher.phone);
      
      const teacherFilePromise = page.waitForEvent('filechooser');
      await page.click('#upload-label');
      const teacherFileChooser = await teacherFilePromise;
      await teacherFileChooser.setFiles(path.join(process.cwd(), 'test_resource.pdf'));
      console.log('[INFO] Teacher PDF file chosen');

      await page.fill('#password', testData.teacher.password);
      await page.fill('#confirm_password', testData.teacher.password);
      await page.click('#signup-btn');
      await LOG_STEP(8, 'Teacher Signup Submitted');
      
      try {
        await expect(page.locator('button:has-text("Processing")')).not.toBeVisible({ timeout: 90000 });
      } catch (_) {}
      
      await LOG_STEP(9, 'Teacher Signup Processing Done');

      if (page.url().includes('/signup/')) {
        const messages = await page.locator('.alert, .toast-message, .error-msg, [class*="error"], [class*="alert"]').allTextContents();
        console.log('[TEACHER SIGNUP ERROR] Still on signup. Messages:', JSON.stringify(messages));
        throw new Error(`[BLOCKER] Teacher Signup failed. Messages: ${JSON.stringify(messages)}`);
      }

      await expect(page).toHaveURL(/login/, { timeout: 30000 });
      await LOG_STEP(10, 'Teacher Signup SUCCESS — Redirected to Login');

      // ============================================================
      // PHASE 3: ADMIN APPROVAL
      // ============================================================
      await LOG_STEP(11, 'Admin Login Started');
      await page.goto('/customadmin/portal-secure-access/');
      await LOG_STEP(12, 'Admin Login Page Loaded');
      
      await page.fill('input[name="username"]', testData.admin.username);
      await page.fill('input[name="password"]', testData.admin.password);
      await page.click('button[type="submit"]');
      
      // admin_dashboard immediately redirects to manage_students — check for either
      // admin_dashboard redirects to manage_students — check either
      await expect(page).toHaveURL(/\/customadmin\/(dashboard\/|students\/?)/, { timeout: 60000 });
      await LOG_STEP(13, 'Admin Login SUCCESS');

      // Approve Student
      // Correct URL: pending/ not pending/students/ — see custom_admin/urls.py
      await page.goto('/customadmin/pending/');
      await LOG_STEP(14, 'Pending Students Page Loaded');
      
      const studentRow = page.locator('tr', { hasText: testData.student.username });
      const studentRowExists = await studentRow.count() > 0;
      console.log(`[INFO] Student row found: ${studentRowExists}`);
      
      if (!studentRowExists) {
        // Log all rows for debugging
        const allRows = await page.locator('table tr').allTextContents();
        console.log('[DEBUG] All table rows:', JSON.stringify(allRows.slice(0, 10)));
        throw new Error(`[BLOCKER] Student "${testData.student.username}" not found in pending students table`);
      }
      
      // Extract accept_user URL from onclick and navigate directly (more reliable than modal)
      const studentApproveLink = studentRow.getByRole('link', { name: 'Approve' });
      const onclickAttr = await studentApproveLink.getAttribute('onclick');
      console.log('[INFO] Student approve onclick:', onclickAttr);
      // Extract URL from onclick: window.location.href = '...'
      const urlMatch = onclickAttr?.match(/window\.location\.href\s*=\s*['"]([^'"]+)['"]/)
                    ?? onclickAttr?.match(/href:\s*['"]([^'"]+)['"]/)
                    ?? onclickAttr?.match(/['"](\/(customadmin|accounts)[^'"]+)['"]/);
      if (urlMatch && urlMatch[1]) {
        const approveUrl = urlMatch[1];
        console.log('[INFO] Navigating to student approval URL:', approveUrl);
        await page.goto(approveUrl);
      } else {
        // Fallback: click and handle modal
        await studentApproveLink.click();
        const backdrop = page.locator('.confirm-backdrop');
        if (await backdrop.isVisible({ timeout: 5000 }).catch(() => false)) {
          await page.locator('.confirm-btn-ok').click();
        }
      }
      await expect(page).toHaveURL(/customadmin/, { timeout: 30000 });
      await LOG_STEP(17, 'Student Approved Successfully');

      // Approve Teacher  
      await page.goto('/customadmin/pending/teachers/'); // correct URL for teachers
      await LOG_STEP(18, 'Pending Teachers Page Loaded');
      
      const teacherRow = page.locator('tr', { hasText: testData.teacher.username });
      const teacherRowExists = await teacherRow.count() > 0;
      console.log(`[INFO] Teacher row found: ${teacherRowExists}`);
      
      if (!teacherRowExists) {
        const allRows = await page.locator('table tr').allTextContents();
        console.log('[DEBUG] All teacher table rows:', JSON.stringify(allRows.slice(0, 10)));
        throw new Error(`[BLOCKER] Teacher "${testData.teacher.username}" not found in pending teachers table`);
      }

      // Extract accept_user URL from onclick and navigate directly
      const teacherApproveLink = teacherRow.getByRole('link', { name: 'Approve' });
      const teacherOnclick = await teacherApproveLink.getAttribute('onclick');
      console.log('[INFO] Teacher approve onclick:', teacherOnclick);
      const teacherUrlMatch = teacherOnclick?.match(/window\.location\.href\s*=\s*['"]([^'"]+)['"]/);
      if (teacherUrlMatch && teacherUrlMatch[1]) {
        console.log('[INFO] Navigating to teacher approval URL:', teacherUrlMatch[1]);
        await page.goto(teacherUrlMatch[1]);
      } else {
        await teacherApproveLink.click();
        const backdrop = page.locator('.confirm-backdrop');
        if (await backdrop.isVisible({ timeout: 5000 }).catch(() => false)) {
          await page.locator('.confirm-btn-ok').click();
        }
      }
      await expect(page).toHaveURL(/customadmin/, { timeout: 30000 });
      await LOG_STEP(21, 'Teacher Approved Successfully');

      // ============================================================
      // PHASE 4: TEACHER LOGIN & CONTENT CREATION
      // ============================================================
      // Explicit logout first to destroy the admin server-side session
      await context.clearCookies();
      await page.goto('/customadmin/logout/');
      await LOG_STEP(22, 'Teacher Portal Login Started — Session Cleared');
      await page.goto('/teacher/login/');
      await LOG_STEP(23, 'Teacher Login Page Loaded');
      
      await page.fill('#username', testData.teacher.username);
      await page.fill('#password', testData.teacher.password);

      // Try multiple selectors for the login button
      const loginBtn = page.locator('#loginBtn, button[type="submit"], input[type="submit"]').first();
      await loginBtn.click();
      
      await expect(page).toHaveURL(/\/teacher\/dashboard/, { timeout: 30000 });
      await LOG_STEP(24, 'Teacher Login SUCCESS');

      // Create Course
      await page.goto('/teacher/courses/create/');
      await LOG_STEP(25, 'Course Create Page Loaded');
      
      await page.fill('input[name="title"]', testData.course.title);
      await page.fill('textarea[name="description"]', testData.course.description);
      await page.selectOption('select[name="category"]', { index: 1 });
      await page.click('button[type="submit"]');
      await LOG_STEP(26, 'Course Submitted');

      // Course should now exist
      await page.goto('/teacher/courses/');
      await LOG_STEP(27, 'My Courses Page Loaded');
      await expect(page.locator(`text=${testData.course.title}`)).toBeVisible({ timeout: 15000 });
      await LOG_STEP(28, 'Course Created Verified');

      console.log('\n===== WORKFLOW MAP =====');
      console.log('✅ Student Signup');
      console.log('✅ Teacher Signup');
      console.log('✅ Admin Login');
      console.log('✅ Student Approved');
      console.log('✅ Teacher Approved');
      console.log('✅ Teacher Login');
      console.log('✅ Course Created');
      console.log('⏳ Lesson, Resource, Student Access (not tested in audit)');
      console.log('\nVisited URLs:');
      visitedURLs.forEach((u, i) => console.log(`  ${i + 1}. ${u}`));

    } catch (error: any) {
      const url = page.url();
      const title = await page.title().catch(() => 'N/A');
      console.error(`\n===== [FAILURE] =====`);
      console.error(`ERROR MESSAGE: ${error.message}`);
      console.error(`URL AT FAILURE: ${url}`);
      console.error(`PAGE TITLE AT FAILURE: ${title}`);
      console.error(`\nComplete URL visit log:`);
      visitedURLs.forEach((u, i) => console.error(`  ${i + 1}. ${u}`));
      await page.screenshot({ path: 'screenshots/FAILURE_screenshot.png', fullPage: true });
      throw error;
    }
  });
});
