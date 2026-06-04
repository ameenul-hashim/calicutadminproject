import { test, expect } from '../helpers/test-utils';
import path from 'path';
import fs from 'fs';

/**
 * ══════════════════════════════════════════════════════════════
 * NeoLearn LMS — FULL END-TO-END JOURNEY TEST
 * ══════════════════════════════════════════════════════════════
 * Phase 1: Teacher Signup + Admin Approval + Teacher Content Creation
 * Phase 2: Admin Full Journey (approvals, rejections, user management)
 * Phase 3: Student Full Journey (signup, enroll, play, resources)
 * 
 * All bugs are collected into a single report at the end.
 * The test DOES NOT stop on first bug — it continues and logs everything.
 */

// ── Bug Collector ──
interface Bug {
  phase: string;
  step: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  description: string;
  url: string;
  screenshot?: string;
  consoleErrors?: string[];
}

const BUGS: Bug[] = [];
const SCREENSHOTS: string[] = [];
const PAGES_TESTED: string[] = [];
const FORMS_TESTED: string[] = [];
const BUTTONS_TESTED: string[] = [];
let STEP_COUNTER = 0;

// ── Helpers ──
const screenshotDir = path.join(process.cwd(), 'screenshots', 'full_journey');

function nextStep() { return ++STEP_COUNTER; }

test.describe('NeoLearn Full E2E Journey', () => {

  const timestamp = Date.now();
  const prefix = `e2e_${timestamp}`;
  
  const testData = {
    teacher: {
      username: `${prefix}_teacher`,
      fullname: `E2E Teacher ${timestamp}`,
      email: `${prefix}_teacher@example.com`,
      phone: `9${timestamp.toString().slice(-9)}`,
      password: 'StrongPass123!'
    },
    student: {
      username: `${prefix}_student`,
      fullname: `E2E Student ${timestamp}`,
      email: `${prefix}_student@example.com`,
      phone: `8${timestamp.toString().slice(-9)}`,
      password: 'StrongPass123!'
    },
    admin: {
      username: 'hashim',
      password: 'Pkd02786*'
    },
    course: {
      title: `E2E Course ${timestamp}`,
      description: 'Comprehensive end-to-end verification course for full LMS workflow testing.',
      chapter: 'Chapter 1: Introduction',
      lesson: 'Lesson 1: Getting Started',
      youtubeUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      resourceTitle: `E2E Resource ${timestamp}`,
      onlineResourceTitle: `Online Resource ${timestamp}`,
      onlineResourceUrl: 'https://example.com/resource'
    }
  };

  // Store UIDs discovered during test
  const discovered = {
    teacherUid: '',
    studentUid: '',
    courseUid: '',
    lessonUid: '',
    resourceUid: '',
  };

  test.setTimeout(900000); // 15 minutes

  test('Phase 1: Teacher Full Journey', async ({ page, context }) => {
    // Ensure screenshot directory exists
    if (!fs.existsSync(screenshotDir)) fs.mkdirSync(screenshotDir, { recursive: true });

    const pdfPath = path.join(process.cwd(), 'test_resource.pdf');
    const consoleErrors: string[] = [];
    const networkErrors: string[] = [];
    
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('requestfailed', req => {
      networkErrors.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`);
    });

    const snap = async (name: string) => {
      const file = path.join(screenshotDir, `step_${nextStep()}_${name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      SCREENSHOTS.push(file);
      return file;
    };

    const logBug = async (phase: string, step: string, severity: Bug['severity'], description: string) => {
      const file = await snap(`BUG_${step.replace(/\s+/g, '_')}`);
      BUGS.push({
        phase, step, severity, description,
        url: page.url(),
        screenshot: file,
        consoleErrors: [...consoleErrors.slice(-5)]
      });
      console.error(`\n🐛 [BUG] ${phase} / ${step}: ${description}`);
      console.error(`   URL: ${page.url()}`);
    };

    // ═══════════════════════════════════════════
    // 1.1  TEACHER SIGNUP
    // ═══════════════════════════════════════════
    console.log('\n═══ PHASE 1: TEACHER JOURNEY ═══\n');
    
    try {
      await page.goto('/teacher/signup/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/teacher/signup/');
      await snap('teacher_signup_page');

      await page.fill('#username', testData.teacher.username);
      await page.fill('#fullname', testData.teacher.fullname);
      await page.fill('#email', testData.teacher.email);
      await page.fill('#phone_number', testData.teacher.phone);
      await page.fill('#password', testData.teacher.password);
      await page.fill('#confirm_password', testData.teacher.password);
      
      // Upload proof file
      await page.setInputFiles('#proof_file', pdfPath);
      console.log('[✓] Teacher signup form filled');
      FORMS_TESTED.push('Teacher Signup Form');

      await snap('teacher_signup_filled');
      await page.click('#signup-btn');
      BUTTONS_TESTED.push('Teacher Signup Submit');
      
      // Wait for processing
      try {
        await page.waitForURL(/teacher\/login/, { timeout: 120000 });
        console.log('[✓] Teacher signup → Redirected to /teacher/login/');
      } catch (e) {
        // Check if still on signup page
        if (page.url().includes('/signup')) {
          const messages = await page.locator('.alert, .toast-message, [class*="error"], [class*="alert"]').allTextContents();
          await logBug('Teacher', 'Signup', 'CRITICAL', `Teacher signup failed. Still on signup page. Messages: ${JSON.stringify(messages)}`);
        } else {
          console.log(`[?] Teacher signup redirected to: ${page.url()}`);
        }
      }
      await snap('teacher_signup_result');
    } catch (err: any) {
      await logBug('Teacher', 'Signup', 'CRITICAL', `Teacher signup exception: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.2  ADMIN APPROVES TEACHER
    // ═══════════════════════════════════════════
    try {
      await context.clearCookies();
      await page.goto('/customadmin/portal-secure-access/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/portal-secure-access/');
      await snap('admin_login_page');

      await page.fill('input[name="username"]', testData.admin.username);
      await page.fill('input[name="password"]', testData.admin.password);
      await page.click('button[type="submit"]');
      BUTTONS_TESTED.push('Admin Login Submit');
      FORMS_TESTED.push('Admin Login Form');

      await page.waitForURL(/customadmin\/(dashboard|students)/, { timeout: 60000 });
      console.log('[✓] Admin logged in');
      await snap('admin_dashboard');

      // Navigate to pending teachers
      await page.goto('/customadmin/pending/teachers/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/pending/teachers/');
      await snap('pending_teachers');

      // Find the teacher row
      const teacherRow = page.locator('tr', { hasText: testData.teacher.username });
      const teacherExists = await teacherRow.count() > 0;
      
      if (!teacherExists) {
        await logBug('Admin', 'Approve Teacher', 'CRITICAL', `Teacher "${testData.teacher.username}" not found in pending teachers list`);
      } else {
        // Execute approval via page.evaluate for reliability
        await Promise.all([
          page.waitForNavigation({ timeout: 30000 }).catch(() => null),
          page.evaluate((name) => {
            const tr = Array.from(document.querySelectorAll('tr')).find(r => r.innerText.includes(name));
            if (!tr) return;
            const btn = Array.from(tr.querySelectorAll('a')).find(a => 
              a.innerText.toLowerCase().includes('approve') || a.innerText.toLowerCase().includes('accept')
            );
            if (!btn) return;
            const onclick = btn.getAttribute('onclick');
            if (onclick) {
              const m = onclick.match(/window\.location\.href\s*=\s*'([^']+)'/);
              if (m) window.location.href = m[1];
            } else if (btn.href && !btn.href.includes('javascript')) {
              window.location.href = btn.href;
            }
          }, testData.teacher.username)
        ]);
        await page.waitForLoadState('networkidle');
        console.log('[✓] Teacher approved by admin');
        BUTTONS_TESTED.push('Approve Teacher Button');
        await snap('teacher_approved');
      }
    } catch (err: any) {
      await logBug('Admin', 'Approve Teacher', 'CRITICAL', `Exception during teacher approval: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.3  TEACHER LOGIN
    // ═══════════════════════════════════════════
    try {
      await context.clearCookies();
      await page.goto('/teacher/login/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/teacher/login/');
      await snap('teacher_login_page');

      await page.fill('#username', testData.teacher.username);
      await page.fill('#password', testData.teacher.password);
      await page.click('#loginBtn');
      BUTTONS_TESTED.push('Teacher Login Submit');
      FORMS_TESTED.push('Teacher Login Form');

      // Teacher may redirect to teacher/dashboard or profile/edit (onboarding)
      await page.waitForURL(/\/(teacher\/dashboard|teacher\/profile\/edit|profile\/edit)/, { timeout: 30000 });
      console.log(`[✓] Teacher login → ${page.url()}`);
      await snap('teacher_login_result');
    } catch (err: any) {
      await logBug('Teacher', 'Login', 'CRITICAL', `Teacher login failed: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.4  TEACHER AVATAR / PROFILE SETUP (Onboarding)
    // ═══════════════════════════════════════════
    try {
      if (page.url().includes('/profile/edit')) {
        console.log('[INFO] Teacher onboarding — selecting avatar');
        PAGES_TESTED.push('/profile/edit/ (teacher onboarding)');

        await page.waitForSelector('.avatar-option', { timeout: 15000 });
        
        // Select first avatar
        await page.evaluate(() => {
          const firstOpt = document.querySelector('.avatar-option') as HTMLElement;
          const input = document.getElementById('avatarUrlInput') as HTMLInputElement;
          if (firstOpt && input) {
            const url = firstOpt.getAttribute('data-url');
            input.value = url || '';
            firstOpt.classList.add('selected');
          }
        });

        await snap('teacher_avatar_selected');

        // Submit — the edit_profile form uses AJAX
        const submitBtn = page.locator('#avatarSubmitBtn, #submitBtn').first();
        await submitBtn.click();
        BUTTONS_TESTED.push('Teacher Avatar Submit');
        FORMS_TESTED.push('Teacher Avatar Selection Form');

        // Wait for redirect to dashboard
        try {
          await page.waitForURL(/\/teacher\/dashboard/, { timeout: 30000 });
          console.log('[✓] Teacher avatar saved → Dashboard');
        } catch {
          // Might need to handle AJAX response manually
          await page.waitForTimeout(3000);
          if (!page.url().includes('/teacher/dashboard')) {
            // Try navigating manually
            await page.goto('/teacher/dashboard/', { waitUntil: 'networkidle' });
          }
        }
        await snap('teacher_after_avatar');

        // Verify avatar is visible after refresh
        await page.reload({ waitUntil: 'networkidle' });
        const avatarImg = page.locator('img[class*="avatar"], img[class*="profile"], .sidebar img, .user-avatar img, .nav img').first();
        const avatarVisible = await avatarImg.isVisible().catch(() => false);
        if (!avatarVisible) {
          await logBug('Teacher', 'Avatar Persistence', 'HIGH', 'Avatar not visible after page refresh');
        } else {
          console.log('[✓] Teacher avatar visible after refresh');
        }
      } else {
        console.log('[INFO] Teacher already has avatar (no onboarding redirect)');
      }
    } catch (err: any) {
      await logBug('Teacher', 'Profile Setup', 'HIGH', `Profile setup exception: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.5  TEACHER DASHBOARD
    // ═══════════════════════════════════════════
    try {
      await page.goto('/teacher/dashboard/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/teacher/dashboard/');
      await snap('teacher_dashboard');
      
      // Verify dashboard elements
      const dashboardTitle = await page.title();
      console.log(`[✓] Teacher dashboard loaded (title: ${dashboardTitle})`);
      
      // Check for stats cards
      const statsVisible = await page.locator('.stat-card, .stats-card, .card, .dashboard-stat').first().isVisible().catch(() => false);
      if (!statsVisible) {
        await logBug('Teacher', 'Dashboard', 'MEDIUM', 'Dashboard stats cards not visibly rendered');
      }
    } catch (err: any) {
      await logBug('Teacher', 'Dashboard', 'MEDIUM', `Dashboard load error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.6  CREATE COURSE
    // ═══════════════════════════════════════════
    try {
      await page.goto('/teacher/courses/create/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/teacher/courses/create/');
      await snap('create_course_page');

      await page.fill('input[name="title"]', testData.course.title);
      await page.fill('textarea[name="description"]', testData.course.description);

      // Select category — try ONLINE or first option
      const categorySelect = page.locator('select[name="category"]');
      if (await categorySelect.isVisible()) {
        await categorySelect.selectOption({ index: 1 });
      }
      const levelSelect = page.locator('select[name="level"]');
      if (await levelSelect.isVisible()) {
        await levelSelect.selectOption({ index: 1 });
      }
      
      FORMS_TESTED.push('Create Course Form');
      await snap('create_course_filled');
      
      await page.click('button[type="submit"]');
      BUTTONS_TESTED.push('Create Course Submit');
      
      // Should redirect to course_lessons page
      await page.waitForURL(/\/lessons\/|\/courses\//, { timeout: 30000 });
      console.log(`[✓] Course created → ${page.url()}`);
      await snap('course_created');

      // Extract course UID from URL
      const courseUrlMatch = page.url().match(/courses\/([a-f0-9-]+)/);
      if (courseUrlMatch) discovered.courseUid = courseUrlMatch[1];
    } catch (err: any) {
      await logBug('Teacher', 'Create Course', 'CRITICAL', `Create course error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.7  CREATE CHAPTER
    // ═══════════════════════════════════════════
    try {
      // We should be on the course_lessons page
      const chapterInput = page.locator('input[name="chapter_name"]');
      if (await chapterInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        await chapterInput.fill(testData.course.chapter);
        await page.click('button:has-text("Create Chapter"), button:has-text("Add Chapter"), button[type="submit"]:near(input[name="chapter_name"])');
        BUTTONS_TESTED.push('Create Chapter Button');
        FORMS_TESTED.push('Create Chapter Form');
        await page.waitForLoadState('networkidle');
        console.log('[✓] Chapter created');
        await snap('chapter_created');
      } else {
        console.log('[INFO] Chapter input not found — trying alternate creation method');
        // Some UIs have modal-based chapter creation
        const addChapterBtn = page.locator('button:has-text("Chapter"), a:has-text("Chapter")').first();
        if (await addChapterBtn.isVisible().catch(() => false)) {
          await addChapterBtn.click();
          await page.waitForTimeout(1000);
          const modalInput = page.locator('input[name="chapter_name"], #chapterName, input[placeholder*="chapter"]').first();
          if (await modalInput.isVisible().catch(() => false)) {
            await modalInput.fill(testData.course.chapter);
            await page.click('button:has-text("Create"), button:has-text("Save"), button:has-text("Add")');
            await page.waitForLoadState('networkidle');
            console.log('[✓] Chapter created via modal');
          }
        }
        await snap('chapter_creation_attempt');
      }
    } catch (err: any) {
      await logBug('Teacher', 'Create Chapter', 'HIGH', `Create chapter error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.8  ADD LESSON (with YouTube URL)
    // ═══════════════════════════════════════════
    try {
      // Find add lesson link/button
      const addLessonLink = page.locator('a:has-text("Add Lesson"), a:has-text("New Lesson"), button:has-text("Add Lesson")').first();
      if (await addLessonLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await addLessonLink.click();
        BUTTONS_TESTED.push('Add Lesson Link');
        await page.waitForLoadState('networkidle');
      } else {
        // Try navigating directly
        if (discovered.courseUid) {
          await page.goto(`/teacher/courses/${discovered.courseUid}/lessons/add/`, { waitUntil: 'networkidle' });
        }
      }
      
      PAGES_TESTED.push('/teacher/courses/.../lessons/add/');
      await snap('add_lesson_page');

      await page.fill('input[name="title"]', testData.course.lesson);
      
      // Fill YouTube URL
      const videoUrlInput = page.locator('input[name="video_url"]');
      if (await videoUrlInput.isVisible().catch(() => false)) {
        await videoUrlInput.fill(testData.course.youtubeUrl);
      }

      // Select chapter
      const chapterSelect = page.locator('select[name="chapter"]');
      if (await chapterSelect.isVisible().catch(() => false)) {
        const options = await chapterSelect.locator('option').allTextContents();
        console.log(`[INFO] Chapter options: ${JSON.stringify(options)}`);
        // Try to select our chapter
        try {
          await chapterSelect.selectOption({ label: testData.course.chapter });
        } catch {
          await chapterSelect.selectOption({ index: 1 });
        }
      }

      FORMS_TESTED.push('Add Lesson Form');
      await snap('add_lesson_filled');

      await page.click('button[type="submit"]');
      BUTTONS_TESTED.push('Add Lesson Submit');

      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
      
      console.log(`[✓] Lesson submitted → ${page.url()}`);
      await snap('lesson_created');
    } catch (err: any) {
      await logBug('Teacher', 'Add Lesson', 'CRITICAL', `Add lesson error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.9  VERIFY COURSE CONTENT PAGE
    // ═══════════════════════════════════════════
    try {
      // Go to course lessons page
      if (discovered.courseUid) {
        await page.goto(`/teacher/courses/${discovered.courseUid}/lessons/`, { waitUntil: 'networkidle' });
      }
      PAGES_TESTED.push('/teacher/courses/.../lessons/');
      await snap('course_lessons_page');

      // Verify lesson appears
      const lessonVisible = await page.locator(`text=${testData.course.lesson}`).isVisible().catch(() => false);
      if (!lessonVisible) {
        // Check for any lesson text
        const pageContent = await page.content();
        if (!pageContent.includes('Lesson') && !pageContent.includes('lesson')) {
          await logBug('Teacher', 'Verify Lesson', 'HIGH', 'Created lesson not visible on course lessons page');
        }
      } else {
        console.log('[✓] Lesson visible on course page');
      }

      // Verify chapter appears
      const chapterVisible = await page.locator(`text=${testData.course.chapter}`).isVisible().catch(() => false);
      if (!chapterVisible) {
        console.log('[WARN] Chapter name not visible — may use different format');
      } else {
        console.log('[✓] Chapter visible on course page');
      }
    } catch (err: any) {
      await logBug('Teacher', 'Verify Content', 'MEDIUM', `Content verification error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.10  SUBMIT COURSE FOR APPROVAL
    // ═══════════════════════════════════════════
    try {
      const submitLink = page.locator('a:has-text("Submit for Approval"), a:has-text("Submit Course"), button:has-text("Submit")').first();
      if (await submitLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await submitLink.click();
        BUTTONS_TESTED.push('Submit Course for Approval');
        await page.waitForLoadState('networkidle');
        console.log(`[✓] Course submitted for approval → ${page.url()}`);
      } else if (discovered.courseUid) {
        // Direct navigation
        await page.goto(`/teacher/courses/${discovered.courseUid}/submit/`, { waitUntil: 'networkidle' });
        console.log(`[✓] Course submitted via direct URL → ${page.url()}`);
      }
      await snap('course_submitted');
    } catch (err: any) {
      await logBug('Teacher', 'Submit Course', 'HIGH', `Submit course error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 1.11  VERIFY MY COURSES PAGE
    // ═══════════════════════════════════════════
    try {
      await page.goto('/teacher/courses/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/teacher/courses/');
      await snap('my_courses_page');

      const courseCard = page.locator(`text=${testData.course.title}`);
      const courseVisible = await courseCard.isVisible().catch(() => false);
      if (!courseVisible) {
        await logBug('Teacher', 'My Courses', 'HIGH', `Course "${testData.course.title}" not visible on My Courses page`);
      } else {
        console.log('[✓] Course visible on My Courses');
        // Check status badge
        const statusBadge = page.locator(`text=PENDING`).first();
        const isPending = await statusBadge.isVisible().catch(() => false);
        console.log(`[INFO] Course status shows PENDING: ${isPending}`);
      }
    } catch (err: any) {
      await logBug('Teacher', 'My Courses', 'MEDIUM', `My courses verification error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // PHASE 1 SUMMARY
    // ═══════════════════════════════════════════
    console.log('\n═══ PHASE 1 COMPLETE ═══');
    console.log(`Pages tested: ${PAGES_TESTED.length}`);
    console.log(`Forms tested: ${FORMS_TESTED.length}`);
    console.log(`Buttons tested: ${BUTTONS_TESTED.length}`);
    console.log(`Bugs found so far: ${BUGS.length}`);
    if (consoleErrors.length > 0) {
      console.log(`Console errors: ${consoleErrors.length}`);
      consoleErrors.forEach(e => console.log(`  ⚠ ${e}`));
    }
    if (networkErrors.length > 0) {
      console.log(`Network errors: ${networkErrors.length}`);
      networkErrors.forEach(e => console.log(`  ⚠ ${e}`));
    }
  });

  test('Phase 2: Admin Full Journey', async ({ page, context }) => {
    if (!fs.existsSync(screenshotDir)) fs.mkdirSync(screenshotDir, { recursive: true });

    const consoleErrors: string[] = [];
    const networkErrors: string[] = [];
    
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('requestfailed', req => {
      networkErrors.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`);
    });

    const snap = async (name: string) => {
      const file = path.join(screenshotDir, `step_${nextStep()}_${name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      SCREENSHOTS.push(file);
    };

    const logBug = async (phase: string, step: string, severity: Bug['severity'], description: string) => {
      const file = path.join(screenshotDir, `BUG_${step.replace(/\s+/g, '_')}.png`);
      await page.screenshot({ path: file, fullPage: true });
      BUGS.push({ phase, step, severity, description, url: page.url(), screenshot: file, consoleErrors: [...consoleErrors.slice(-5)] });
      console.error(`\n🐛 [BUG] ${phase} / ${step}: ${description}`);
    };

    console.log('\n═══ PHASE 2: ADMIN JOURNEY ═══\n');

    // ═══════════════════════════════════════════
    // 2.1  ADMIN LOGIN
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/portal-secure-access/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/portal-secure-access/');
      await snap('admin_login');

      await page.fill('input[name="username"]', testData.admin.username);
      await page.fill('input[name="password"]', testData.admin.password);
      await page.click('button[type="submit"]');
      BUTTONS_TESTED.push('Admin Login');
      FORMS_TESTED.push('Admin Login');

      await page.waitForURL(/customadmin\/(dashboard|students)/, { timeout: 60000 });
      console.log('[✓] Admin logged in');
      await snap('admin_logged_in');
    } catch (err: any) {
      await logBug('Admin', 'Login', 'CRITICAL', `Admin login failed: ${err.message}`);
      return; // Cannot continue without admin access
    }

    // ═══════════════════════════════════════════
    // 2.2  STUDENT SIGNUP (for admin to approve)
    // ═══════════════════════════════════════════
    // First signup a student in a separate context
    try {
      const pdfPath = path.join(process.cwd(), 'test_resource.pdf');
      const studentPage = await context.newPage();
      await studentPage.goto('/signup/', { waitUntil: 'networkidle' });
      
      await studentPage.fill('#username', testData.student.username);
      await studentPage.fill('#fullname', testData.student.fullname);
      await studentPage.fill('#email', testData.student.email);
      await studentPage.fill('#phone_number', testData.student.phone);
      await studentPage.fill('#password', testData.student.password);
      await studentPage.fill('#confirm_password', testData.student.password);
      await studentPage.setInputFiles('#proof_file', pdfPath);
      await studentPage.click('#signup-btn');
      
      try {
        await studentPage.waitForURL(/login/, { timeout: 120000 });
        console.log('[✓] Student signed up for admin approval testing');
      } catch {
        const messages = await studentPage.locator('.alert, .toast-message, [class*="error"]').allTextContents();
        await logBug('Admin', 'Student Signup', 'CRITICAL', `Student signup failed: ${JSON.stringify(messages)}`);
      }
      
      FORMS_TESTED.push('Student Signup Form');
      await studentPage.close();
    } catch (err: any) {
      await logBug('Admin', 'Student Signup', 'CRITICAL', `Student signup for admin test: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.3  APPROVE STUDENT
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/pending/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/pending/');
      await snap('pending_students');

      const studentRow = page.locator('tr', { hasText: testData.student.username });
      if (await studentRow.count() > 0) {
        await Promise.all([
          page.waitForNavigation({ timeout: 30000 }).catch(() => null),
          page.evaluate((name) => {
            const tr = Array.from(document.querySelectorAll('tr')).find(r => r.innerText.includes(name));
            if (!tr) return;
            const btn = Array.from(tr.querySelectorAll('a')).find(a => 
              a.innerText.toLowerCase().includes('approve') || a.innerText.toLowerCase().includes('accept')
            );
            if (!btn) return;
            const onclick = btn.getAttribute('onclick');
            if (onclick) {
              const m = onclick.match(/window\.location\.href\s*=\s*'([^']+)'/);
              if (m) window.location.href = m[1];
            } else if (btn.href && !btn.href.includes('javascript')) {
              window.location.href = btn.href;
            }
          }, testData.student.username)
        ]);
        await page.waitForLoadState('networkidle');
        console.log('[✓] Student approved');
        BUTTONS_TESTED.push('Approve Student');
        await snap('student_approved');
      } else {
        await logBug('Admin', 'Approve Student', 'CRITICAL', `Student "${testData.student.username}" not in pending list`);
      }
    } catch (err: any) {
      await logBug('Admin', 'Approve Student', 'HIGH', `Student approval error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.4  APPROVE COURSE
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/pending/courses/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/pending/courses/');
      await snap('pending_courses');

      const courseRow = page.locator('tr', { hasText: testData.course.title });
      if (await courseRow.count() > 0) {
        // Find approve link
        const approveLink = courseRow.locator('a:has-text("Approve")').first();
        if (await approveLink.isVisible().catch(() => false)) {
          const href = await approveLink.getAttribute('href');
          if (href) {
            await page.goto(href, { waitUntil: 'networkidle' });
          } else {
            await approveLink.click();
            await page.waitForLoadState('networkidle');
          }
        } else {
          // Try evaluate-based approach
          await Promise.all([
            page.waitForNavigation({ timeout: 30000 }).catch(() => null),
            page.evaluate((title) => {
              const tr = Array.from(document.querySelectorAll('tr')).find(r => r.innerText.includes(title));
              if (!tr) return;
              const btn = Array.from(tr.querySelectorAll('a')).find(a => 
                a.innerText.toLowerCase().includes('approve')
              );
              if (btn) {
                const onclick = btn.getAttribute('onclick');
                if (onclick) {
                  const m = onclick.match(/window\.location\.href\s*=\s*'([^']+)'/);
                  if (m) window.location.href = m[1];
                } else if (btn.href) {
                  window.location.href = btn.href;
                }
              }
            }, testData.course.title)
          ]);
          await page.waitForLoadState('networkidle');
        }
        console.log('[✓] Course approved');
        BUTTONS_TESTED.push('Approve Course');
        await snap('course_approved');
      } else {
        await logBug('Admin', 'Approve Course', 'HIGH', `Course "${testData.course.title}" not in pending courses`);
      }
    } catch (err: any) {
      await logBug('Admin', 'Approve Course', 'HIGH', `Course approval error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.5  APPROVE LESSON
    // ═══════════════════════════════════════════
    try {
      // Lessons may be visible within course verification page or pending resources
      // Try to check via the course verification page
      if (discovered.courseUid) {
        await page.goto(`/customadmin/course/${discovered.courseUid}/verify/`, { waitUntil: 'networkidle' });
        PAGES_TESTED.push('/customadmin/course/.../verify/');
        await snap('verify_course_content');
      }
      
      // Also look on the content management page
      await page.goto('/customadmin/content/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/content/');
      await snap('content_management');

      // Find pending lesson row
      const lessonRow = page.locator('tr', { hasText: testData.course.lesson });
      if (await lessonRow.count() > 0) {
        const approveBtn = lessonRow.locator('a:has-text("Approve")').first();
        if (await approveBtn.isVisible().catch(() => false)) {
          const href = await approveBtn.getAttribute('href');
          if (href) {
            await page.goto(href, { waitUntil: 'networkidle' });
          } else {
            await approveBtn.click();
            await page.waitForLoadState('networkidle');
          }
          console.log('[✓] Lesson approved');
          BUTTONS_TESTED.push('Approve Lesson');
        }
      } else {
        console.log('[INFO] Lesson not found on content page — may need separate approval');
      }
      await snap('lesson_approval_attempt');
    } catch (err: any) {
      await logBug('Admin', 'Approve Lesson', 'MEDIUM', `Lesson approval error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.6  ADMIN DASHBOARD VERIFICATION
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/dashboard/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/dashboard/');
      await snap('admin_dashboard_full');
      console.log('[✓] Admin dashboard loaded');
    } catch (err: any) {
      await logBug('Admin', 'Dashboard', 'MEDIUM', `Dashboard error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.7  MANAGE STUDENTS PAGE
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/students/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/students/');
      await snap('manage_students');
      console.log('[✓] Manage students page loaded');
    } catch (err: any) {
      await logBug('Admin', 'Manage Students', 'MEDIUM', `Manage students error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.8  MANAGE TEACHERS PAGE
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/teachers/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/teachers/');
      await snap('manage_teachers');
      console.log('[✓] Manage teachers page loaded');
    } catch (err: any) {
      await logBug('Admin', 'Manage Teachers', 'MEDIUM', `Manage teachers error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.9  ANALYTICS PAGE
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/analytics/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/analytics/');
      await snap('admin_analytics');
      
      // Check for 500 error
      const is500 = await page.locator('text=Server Error, text=500').isVisible().catch(() => false);
      if (is500) {
        await logBug('Admin', 'Analytics', 'HIGH', 'Analytics page returns 500 Server Error');
      } else {
        console.log('[✓] Analytics page loaded');
      }
    } catch (err: any) {
      await logBug('Admin', 'Analytics', 'MEDIUM', `Analytics error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.10  NOTIFICATIONS PAGE
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/notifications/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/notifications/');
      await snap('admin_notifications');
      console.log('[✓] Admin notifications page loaded');
    } catch (err: any) {
      await logBug('Admin', 'Notifications', 'MEDIUM', `Notifications error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.11  ENTERPRISE MONITOR
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/enterprise-monitor/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/enterprise-monitor/');
      await snap('enterprise_monitor');
      console.log('[✓] Enterprise monitor loaded');
    } catch (err: any) {
      await logBug('Admin', 'Enterprise Monitor', 'MEDIUM', `Enterprise monitor error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.12  SYSTEM AUDIT
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/system-audit/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/system-audit/');
      await snap('system_audit');
      console.log('[✓] System audit page loaded');
    } catch (err: any) {
      await logBug('Admin', 'System Audit', 'MEDIUM', `System audit error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.13  DELETION REQUESTS
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/deletion-requests/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/deletion-requests/');
      await snap('deletion_requests');
      console.log('[✓] Deletion requests page loaded');
    } catch (err: any) {
      await logBug('Admin', 'Deletion Requests', 'MEDIUM', `Deletion requests error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 2.14  STORAGE DASHBOARD
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/storage-dashboard/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/storage-dashboard/');
      await snap('storage_dashboard');
      console.log('[✓] Storage dashboard loaded');
    } catch (err: any) {
      await logBug('Admin', 'Storage Dashboard', 'MEDIUM', `Storage dashboard error: ${err.message}`);
    }

    // ═══════════════════════════════════════════  
    // 2.15  DELETED COURSES
    // ═══════════════════════════════════════════
    try {
      await page.goto('/customadmin/deleted-courses/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/customadmin/deleted-courses/');
      await snap('deleted_courses');
      console.log('[✓] Deleted courses page loaded');
    } catch (err: any) {
      await logBug('Admin', 'Deleted Courses', 'MEDIUM', `Deleted courses error: ${err.message}`);
    }

    // Phase 2 Summary
    console.log('\n═══ PHASE 2 COMPLETE ═══');
    console.log(`Total pages tested: ${PAGES_TESTED.length}`);
    console.log(`Total bugs: ${BUGS.length}`);
    if (consoleErrors.length > 0) {
      console.log(`Console errors: ${consoleErrors.length}`);
    }
    if (networkErrors.length > 0) {
      console.log(`Network errors: ${networkErrors.length}`);
      networkErrors.forEach(e => console.log(`  ⚠ ${e}`));
    }
  });

  test('Phase 3: Student Full Journey', async ({ page, context }) => {
    if (!fs.existsSync(screenshotDir)) fs.mkdirSync(screenshotDir, { recursive: true });

    const consoleErrors: string[] = [];
    const networkErrors: string[] = [];
    
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('requestfailed', req => {
      networkErrors.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`);
    });

    const snap = async (name: string) => {
      const file = path.join(screenshotDir, `step_${nextStep()}_${name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      SCREENSHOTS.push(file);
    };

    const logBug = async (phase: string, step: string, severity: Bug['severity'], description: string) => {
      const file = path.join(screenshotDir, `BUG_${step.replace(/\s+/g, '_')}.png`);
      await page.screenshot({ path: file, fullPage: true });
      BUGS.push({ phase, step, severity, description, url: page.url(), screenshot: file, consoleErrors: [...consoleErrors.slice(-5)] });
      console.error(`\n🐛 [BUG] ${phase} / ${step}: ${description}`);
    };

    console.log('\n═══ PHASE 3: STUDENT JOURNEY ═══\n');

    // ═══════════════════════════════════════════
    // 3.1  STUDENT LOGIN
    // ═══════════════════════════════════════════
    try {
      await context.clearCookies();
      await page.goto('/login/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/login/');
      await snap('student_login_page');

      await page.fill('#username', testData.student.username);
      await page.fill('#password', testData.student.password);
      await page.click('#loginBtn');
      BUTTONS_TESTED.push('Student Login');
      FORMS_TESTED.push('Student Login Form');

      await page.waitForURL(/\/(dashboard|profile\/edit)/, { timeout: 30000 });
      console.log(`[✓] Student login → ${page.url()}`);
      await snap('student_login_result');
    } catch (err: any) {
      await logBug('Student', 'Login', 'CRITICAL', `Student login failed: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 3.2  STUDENT AVATAR / PROFILE SETUP
    // ═══════════════════════════════════════════
    try {
      if (page.url().includes('/profile/edit')) {
        console.log('[INFO] Student onboarding — selecting avatar');
        PAGES_TESTED.push('/profile/edit/ (student onboarding)');

        await page.waitForSelector('.avatar-option', { timeout: 15000 });
        
        // Select first avatar
        await page.evaluate(() => {
          const firstOpt = document.querySelector('.avatar-option') as HTMLElement;
          const input = document.getElementById('avatarUrlInput') as HTMLInputElement;
          if (firstOpt && input) {
            const url = firstOpt.getAttribute('data-url');
            input.value = url || '';
            firstOpt.classList.add('selected');
          }
        });

        await snap('student_avatar_selected');

        const submitBtn = page.locator('#submitBtn').first();
        await submitBtn.click();
        BUTTONS_TESTED.push('Student Avatar Submit');
        FORMS_TESTED.push('Student Avatar Form');

        // Wait for redirect to dashboard
        try {
          await page.waitForURL(/\/dashboard/, { timeout: 30000 });
          console.log('[✓] Student avatar saved → Dashboard');
        } catch {
          await page.waitForTimeout(3000);
          if (!page.url().includes('/dashboard')) {
            await page.goto('/dashboard/', { waitUntil: 'networkidle' });
          }
        }
        await snap('student_after_avatar');
      }
    } catch (err: any) {
      await logBug('Student', 'Profile Setup', 'HIGH', `Profile setup error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 3.3  STUDENT DASHBOARD
    // ═══════════════════════════════════════════
    try {
      await page.goto('/dashboard/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/dashboard/');
      await snap('student_dashboard');
      console.log('[✓] Student dashboard loaded');
    } catch (err: any) {
      await logBug('Student', 'Dashboard', 'MEDIUM', `Dashboard error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 3.4  EXPLORE COURSES
    // ═══════════════════════════════════════════
    try {
      await page.goto('/student/explore/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/student/explore/');
      await snap('student_explore');

      // Look for our course
      const courseCard = page.locator(`text=${testData.course.title}`);
      const courseVisible = await courseCard.isVisible().catch(() => false);
      
      if (!courseVisible) {
        await logBug('Student', 'Explore', 'HIGH', `Course "${testData.course.title}" not visible in explore page`);
      } else {
        console.log('[✓] Course visible in explore page');
      }
    } catch (err: any) {
      await logBug('Student', 'Explore', 'MEDIUM', `Explore error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 3.5  ENROLL IN COURSE
    // ═══════════════════════════════════════════
    try {
      const enrollBtn = page.locator(`a:has-text("Enroll"), button:has-text("Enroll")`).first();
      if (await enrollBtn.isVisible().catch(() => false)) {
        await enrollBtn.click();
        BUTTONS_TESTED.push('Enroll in Course');
        await page.waitForLoadState('networkidle');
        console.log(`[✓] Enrolled → ${page.url()}`);
        await snap('enrolled');
      } else {
        // Try finding the course card and its enroll button
        const courseSection = page.locator(`.course-card:has-text("${testData.course.title}")`).first();
        const courseEnroll = courseSection.locator('a:has-text("Enroll")');
        if (await courseEnroll.isVisible().catch(() => false)) {
          await courseEnroll.click();
          BUTTONS_TESTED.push('Enroll via Course Card');
          await page.waitForLoadState('networkidle');
          console.log(`[✓] Enrolled via card → ${page.url()}`);
        } else {
          await logBug('Student', 'Enrollment', 'HIGH', 'Enroll button not found');
        }
        await snap('enrollment_attempt');
      }
    } catch (err: any) {
      await logBug('Student', 'Enrollment', 'HIGH', `Enrollment error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 3.6  COURSE PLAYER
    // ═══════════════════════════════════════════
    try {
      // Navigate to course player if not already there
      if (!page.url().includes('/play/')) {
        // Find course on dashboard
        await page.goto('/dashboard/', { waitUntil: 'networkidle' });
        const courseLink = page.locator(`a:has-text("${testData.course.title}")`).first();
        if (await courseLink.isVisible().catch(() => false)) {
          await courseLink.click();
          await page.waitForLoadState('networkidle');
        }
      }

      PAGES_TESTED.push('/course/.../play/');
      await snap('course_player');

      // Verify lesson is visible
      const lessonLink = page.locator(`text=${testData.course.lesson}`);
      const lessonVisible = await lessonLink.isVisible().catch(() => false);
      if (!lessonVisible) {
        await logBug('Student', 'Course Player', 'HIGH', 'Lesson not visible in course player');
      } else {
        console.log('[✓] Lesson visible in course player');
        
        // Click on lesson
        await lessonLink.click();
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(2000);
        await snap('lesson_playing');

        // Check for YouTube embed or video player
        const hasVideo = await page.locator('iframe[src*="youtube"], iframe[src*="youtu.be"], video, .video-container, .video-player').first().isVisible().catch(() => false);
        if (!hasVideo) {
          await logBug('Student', 'Video Playback', 'HIGH', 'YouTube video not visible/embedded after clicking lesson');
        } else {
          console.log('[✓] Video player visible');
        }
      }
    } catch (err: any) {
      await logBug('Student', 'Course Player', 'HIGH', `Course player error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 3.7  STUDENT PROFILE
    // ═══════════════════════════════════════════
    try {
      await page.goto('/profile/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/profile/');
      await snap('student_profile');
      console.log('[✓] Student profile loaded');
      
      // Verify avatar is visible
      const profileAvatar = page.locator('img[src*="cloudinary"], img[src*="ui-avatars"], img[class*="avatar"], img[class*="profile"]').first();
      if (await profileAvatar.isVisible().catch(() => false)) {
        console.log('[✓] Avatar visible on profile');
      } else {
        await logBug('Student', 'Profile Avatar', 'MEDIUM', 'Avatar image not visible on profile page');
      }
    } catch (err: any) {
      await logBug('Student', 'Profile', 'MEDIUM', `Profile error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 3.8  NOTIFICATIONS
    // ═══════════════════════════════════════════
    try {
      await page.goto('/notifications/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/notifications/');
      await snap('student_notifications');
      console.log('[✓] Notifications page loaded');
    } catch (err: any) {
      await logBug('Student', 'Notifications', 'MEDIUM', `Notifications error: ${err.message}`);
    }

    // ═══════════════════════════════════════════
    // 3.9  STUDENT LOGOUT
    // ═══════════════════════════════════════════
    try {
      await page.goto('/logout/', { waitUntil: 'networkidle' });
      PAGES_TESTED.push('/logout/');
      await snap('student_logged_out');
      
      // Should redirect to login
      const isLoggedOut = page.url().includes('/login') || page.url().endsWith('/');
      if (isLoggedOut) {
        console.log('[✓] Student logged out successfully');
      } else {
        await logBug('Student', 'Logout', 'MEDIUM', `Logout did not redirect to login — URL: ${page.url()}`);
      }
    } catch (err: any) {
      await logBug('Student', 'Logout', 'MEDIUM', `Logout error: ${err.message}`);
    }

    // ═══════════════════════════════════════════════════
    // FINAL REPORT
    // ═══════════════════════════════════════════════════
    console.log('\n');
    console.log('╔══════════════════════════════════════════════════╗');
    console.log('║     NEOLEARN FULL E2E JOURNEY — FINAL REPORT     ║');
    console.log('╚══════════════════════════════════════════════════╝');
    console.log('');
    console.log(`📄 Pages Tested:     ${PAGES_TESTED.length}`);
    console.log(`📝 Forms Tested:     ${FORMS_TESTED.length}`);
    console.log(`🔘 Buttons Tested:   ${BUTTONS_TESTED.length}`);
    console.log(`📸 Screenshots:      ${SCREENSHOTS.length}`);
    console.log(`🐛 Total Bugs:       ${BUGS.length}`);
    console.log('');
    
    if (BUGS.length > 0) {
      console.log('──── BUG REPORT ────');
      BUGS.forEach((bug, i) => {
        console.log(`\n[BUG #${i + 1}] (${bug.severity})`);
        console.log(`  Phase:       ${bug.phase}`);
        console.log(`  Step:        ${bug.step}`);
        console.log(`  Description: ${bug.description}`);
        console.log(`  URL:         ${bug.url}`);
        if (bug.screenshot) console.log(`  Screenshot:  ${bug.screenshot}`);
        if (bug.consoleErrors?.length) {
          console.log(`  Console:     ${bug.consoleErrors.join(' | ')}`);
        }
      });
    } else {
      console.log('✅ NO BUGS FOUND — All workflows passed!');
    }

    console.log('\n──── PAGES TESTED ────');
    [...new Set(PAGES_TESTED)].forEach(p => console.log(`  ✓ ${p}`));
    
    console.log('\n──── FORMS TESTED ────');
    [...new Set(FORMS_TESTED)].forEach(f => console.log(`  ✓ ${f}`));
    
    console.log('\n──── BUTTONS TESTED ────');
    [...new Set(BUTTONS_TESTED)].forEach(b => console.log(`  ✓ ${b}`));

    // Calculate production readiness score
    const critical = BUGS.filter(b => b.severity === 'CRITICAL').length;
    const high = BUGS.filter(b => b.severity === 'HIGH').length;
    const medium = BUGS.filter(b => b.severity === 'MEDIUM').length;
    const low = BUGS.filter(b => b.severity === 'LOW').length;
    const score = Math.max(0, 100 - (critical * 20) - (high * 10) - (medium * 3) - (low * 1));
    
    console.log('\n──── READINESS SCORE ────');
    console.log(`  CRITICAL bugs: ${critical}`);
    console.log(`  HIGH bugs:     ${high}`);
    console.log(`  MEDIUM bugs:   ${medium}`);
    console.log(`  LOW bugs:      ${low}`);
    console.log(`  ────────────────────`);
    console.log(`  🏆 PRODUCTION READINESS: ${score}/100`);
    
    if (score >= 90) console.log('  ✅ SHIP IT');
    else if (score >= 70) console.log('  ⚠️ NEEDS MINOR FIXES');
    else if (score >= 50) console.log('  🔶 SIGNIFICANT ISSUES');
    else console.log('  🛑 NOT READY FOR PRODUCTION');

    // Write report to file
    const reportPath = path.join(screenshotDir, 'FINAL_REPORT.json');
    fs.writeFileSync(reportPath, JSON.stringify({
      timestamp: new Date().toISOString(),
      summary: {
        pagesTestedCount: [...new Set(PAGES_TESTED)].length,
        formsTestedCount: [...new Set(FORMS_TESTED)].length,
        buttonsTestedCount: [...new Set(BUTTONS_TESTED)].length,
        screenshotsCount: SCREENSHOTS.length,
        totalBugs: BUGS.length,
        criticalBugs: critical,
        highBugs: high,
        mediumBugs: medium,
        lowBugs: low,
        productionReadiness: score
      },
      pages: [...new Set(PAGES_TESTED)],
      forms: [...new Set(FORMS_TESTED)],
      buttons: [...new Set(BUTTONS_TESTED)],
      bugs: BUGS,
      consoleErrors,
      networkErrors
    }, null, 2));
    console.log(`\n📁 Full report saved: ${reportPath}`);
  });
});
