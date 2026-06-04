import { test, expect } from '../helpers/test-utils';
import path from 'path';

/**
 * NeoLearn Content Lifecycle Audit (Senior QA Engineer & LMS Auditor Mode)
 * Focus: Complete Content Lifecycle, CRUD, and UI/DB Consistency.
 */

test.describe('NeoLearn Business Workflow Audit: Content Lifecycle', () => {
    const timestamp = Date.now();
    const prefix = `audit_${timestamp}`;
    const testData = {
        teacher: {
            username: `${prefix}_t`,
            fullname: `Audit Teacher ${timestamp}`,
            email: `${prefix}_t@example.com`,
            phone: `9${timestamp.toString().slice(-9)}`,
            password: 'StrongPassword123!'
        },
        student: {
            username: `${prefix}_s`,
            fullname: `Audit Student ${timestamp}`,
            email: `${prefix}_s@example.com`,
            phone: `8${timestamp.toString().slice(-9)}`,
            password: 'StrongPassword123!'
        },
        admin: {
            username: 'hashim',
            password: 'Pkd02786*'
        }
    };

    test.setTimeout(600000);

    test('LMS Workflow: Complete Lifecycle Audit', async ({ page, context }) => {

        const pdfPath = path.join(process.cwd(), 'test_resource.pdf');

        // --- SIGNUP ---
        await page.goto('/signup/');
        await page.fill('#username', testData.student.username);
        await page.fill('#fullname', testData.student.fullname);
        await page.fill('#email', testData.student.email);
        await page.fill('#phone_number', testData.student.phone);
        await page.fill('#password', testData.student.password);
        await page.fill('#confirm_password', testData.student.password);
        await page.setInputFiles('#proof_file', pdfPath);
        await page.click('#signup-btn');
        await expect(page).toHaveURL(/login/);

        await page.goto('/teacher/signup/');
        await page.fill('#username', testData.teacher.username);
        await page.fill('#fullname', testData.teacher.fullname);
        await page.fill('#email', testData.teacher.email);
        await page.fill('#phone_number', testData.teacher.phone);
        await page.fill('#password', testData.teacher.password);
        await page.fill('#confirm_password', testData.teacher.password);
        await page.setInputFiles('#proof_file', pdfPath);
        await page.click('#signup-btn');
        await expect(page).toHaveURL(/teacher\/login/);

        // --- ADMIN APPROVAL ---
        await page.goto('/customadmin/portal-secure-access/');
        await page.fill('input[name="username"]', testData.admin.username);
        await page.fill('input[name="password"]', testData.admin.password);
        await page.click('button[type="submit"]');

        const approveUser = async (uname, listPath) => {
            await page.goto(listPath);
            await Promise.all([
                page.waitForNavigation(),
                page.evaluate((name) => {
                    const tr = Array.from(document.querySelectorAll('tr')).find(r => r.innerText.includes(name));
                    if (!tr) return;
                    const btn = Array.from(tr.querySelectorAll('a')).find(a => a.innerText.toLowerCase().includes('approve'));
                    if (!btn) return;
                    const onclick = btn.getAttribute('onclick');
                    if (onclick) {
                       const m = onclick.match(/window\.location\.href\s*=\s*'([^']+)'/);
                       if (m) window.location.href = m[1];
                    } else if (btn.href && !btn.href.includes('javascript')) {
                       window.location.href = btn.href;
                    }
                }, uname)
            ]);
            await page.waitForLoadState('networkidle');
        };

        await approveUser(testData.student.username, '/customadmin/pending/');
        await approveUser(testData.teacher.username, '/customadmin/pending/teachers/');

        // --- TEACHER FLOW ---
        await context.clearCookies();
        await page.goto('/teacher/login/');
        await page.fill('#username', testData.teacher.username);
        await page.fill('#password', testData.teacher.password);
        await page.click('#loginBtn');

        await page.waitForURL(/\/(teacher\/dashboard|profile\/edit)/);
        if (page.url().includes('/profile/edit')) {
            console.log('[ONBOARDING] Selecting avatar for teacher...');
            await page.waitForSelector('.avatar-option');
            // Force select first avatar via JS to ensure hidden input is populated
            await page.evaluate(() => {
                const firstOpt = document.querySelector('.avatar-option') as HTMLElement;
                const input = document.getElementById('avatarUrlInput') as HTMLInputElement;
                if (firstOpt && input) {
                    const url = firstOpt.getAttribute('data-url');
                    input.value = url || '';
                    firstOpt.classList.add('selected');
                }
            });
            await page.click('#avatarSubmitBtn');
            await page.waitForURL(/\/teacher\/dashboard/);
        }

        // CREATE COURSE
        await page.goto('/teacher/courses/create/');
        await page.fill('input[name="title"]', `Course ${timestamp}`);
        await page.fill('textarea[name="description"]', 'Audit desc');
        await page.selectOption('select[name="category"]', 'ONLINE');
        await page.selectOption('select[name="level"]', 'Advanced');
        await page.click('button[type="submit"]');
        
        // CHAPTER
        await page.waitForURL(/\/lessons\//);
        await page.fill('input[name="chapter_name"]', 'Chapter 1');
        await page.click('button:has-text("Create Chapter")');

        // LESSON
        await page.click('a:has-text("Add Lesson")');
        await page.fill('input[name="title"]', 'Lesson 1');
        await page.fill('input[name="video_url"]', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
        await page.selectOption('select[name="chapter"]', { label: 'Chapter 1' });
        await page.click('button[type="submit"]');

        // SUBMIT
        await page.click('a:has-text("Submit for Approval")');

        // --- ADMIN APPROVAL ---
        await context.clearCookies();
        await page.goto('/customadmin/portal-secure-access/');
        await page.fill('input[name="username"]', testData.admin.username);
        await page.fill('input[name="password"]', testData.admin.password);
        await page.click('button[type="submit"]');
        await page.goto('/customadmin/pending/courses/');
        await page.click(`tr:has-text("Course ${timestamp}") a:has-text("Approve")`);

        // --- STUDENT ACCESS ---
        await context.clearCookies();
        await page.goto('/login/');
        await page.fill('#username', testData.student.username);
        await page.fill('#password', testData.student.password);
        await page.click('#loginBtn');

        await page.waitForURL(/\/(dashboard|profile\/edit)/);
        if (page.url().includes('/profile/edit/')) {
            console.log('[ONBOARDING] Selecting avatar for student...');
            await page.waitForSelector('.avatar-option');
            await page.evaluate(() => {
                const firstOpt = document.querySelector('.avatar-option') as HTMLElement;
                const input = document.getElementById('avatarUrlInput') as HTMLInputElement;
                if (firstOpt && input) {
                    input.value = firstOpt.getAttribute('data-url') || '';
                }
            });
            await page.click('#submitBtn');
            await page.waitForURL(/\/dashboard/);
        }

        await page.goto('/student/explore/');
        await page.click(`.course-card:has-text("Course ${timestamp}") a:has-text("Enroll Now")`);
        await expect(page).toHaveURL(/\/play\//);
        await expect(page.locator('text=Lesson 1')).toBeVisible();

        console.log('[AUDIT SUCCESSFUL]');
    });
});
