import { test, expect } from '../helpers/test-utils';
import path from 'path';

/**
 * Onboarding Flow Investigation - v2
 * Focus: Force interaction and explicit state logging.
 */

test.describe('Onboarding Profile Investigation', () => {
    const timestamp = Date.now();
    const studentData = {
        username: `inv_s_${timestamp}`,
        fullname: `Audit Student ${timestamp}`,
        email: `inv_s_${timestamp}@example.com`,
        phone: `8${timestamp.toString().slice(-9)}`,
        password: 'StrongPassword123!'
    };
    const adminData = {
        username: 'hashim',
        password: 'Pkd02786*'
    };

    const pdfPath = path.join(process.cwd(), 'test_resource.pdf');

    test.setTimeout(120000);

    test('Student Onboarding Lifecycle', async ({ page, context }) => {
        // --- Signup ---
        await page.goto('/signup/');
        await page.fill('#username', studentData.username);
        await page.fill('#fullname', studentData.fullname);
        await page.fill('#email', studentData.email);
        await page.fill('#phone_number', studentData.phone);
        await page.fill('#password', studentData.password);
        await page.fill('#confirm_password', studentData.password);
        await page.setInputFiles('#proof_file', pdfPath);
        await page.click('#signup-btn');
        await expect(page).toHaveURL(/login/);

        // --- Approve ---
        await page.goto('/customadmin/portal-secure-access/');
        await page.fill('input[name="username"]', adminData.username);
        await page.fill('input[name="password"]', adminData.password);
        await page.click('button[type="submit"]');
        await page.goto('/customadmin/pending/');
        await page.evaluate((uname) => {
            const row = Array.from(document.querySelectorAll('tr')).find(r => r.innerText.includes(uname));
            if (row) {
                const btn = Array.from(row.querySelectorAll('a')).find(a => a.innerText.toLowerCase().includes('approve')) as HTMLAnchorElement;
                if (btn) {
                    const onclick = btn.getAttribute('onclick');
                    if (onclick) {
                        const m = onclick.match(/window\.location\.href\s*=\s*'([^']+)'/);
                        if (m) window.location.href = m[1];
                    } else if (btn.href && !btn.href.includes('javascript')) {
                        window.location.href = btn.href;
                    }
                }
            }
        }, studentData.username);
        await page.waitForLoadState('networkidle');

        // --- First Login ---
        await context.clearCookies();
        await page.goto('/login/');
        await page.fill('#username', studentData.username);
        await page.fill('#password', studentData.password);
        await page.click('#loginBtn');

        await page.waitForURL(/\/profile\/edit/);
        console.log('[DEBUG] On Profile Page');

        // Verify Avatars Exist
        const avatars = page.locator('.avatar-option');
        const count = await avatars.count();
        console.log(`[DEBUG] Found ${count} avatars.`);

        if (count > 0) {
            const firstAvatar = avatars.first();
            const url = await firstAvatar.getAttribute('data-url');
            console.log(`[DEBUG] First Avatar URL: ${url}`);
            
            // Force Click via JS to be absolutely sure
            await page.evaluate(() => {
                const el = document.querySelector('.avatar-option') as HTMLElement;
                if (el) el.click();
            });
            console.log('[ACTION] Performed JS Click on first avatar.');
        }

        await page.waitForTimeout(2000);
        await page.screenshot({ path: 'screenshots/verify_selection.png' });

        // Check if value is set
        const val = await page.inputValue('#avatarUrlInput');
        console.log(`[DEBUG] Hidden Input Value: ${val}`);

        console.log('[ACTION] Submitting Profile...');
        await page.click('#submitBtn');

        await page.waitForTimeout(5000);
        if (page.url().includes('/dashboard')) {
            console.log('[RESULT] SUCCESS reached dashboard');
        } else {
            console.log(`[RESULT] FAILED at ${page.url()}`);
            const toast = await page.locator('.toast-card.toast-error').innerText().catch(() => 'No toast');
            console.log(`[RESULT] Toast Message: ${toast}`);
        }
    });

    test('Teacher Onboarding Lifecycle', async ({ page, context }) => {
        const teacherData = {
            username: `inv_t_${timestamp}`,
            fullname: `Audit Teacher ${timestamp}`,
            email: `inv_t_${timestamp}@example.com`,
            phone: `9${timestamp.toString().slice(-9)}`,
            password: 'StrongPassword123!'
        };

        // --- Signup ---
        await page.goto('/teacher/signup/');
        await page.fill('#username', teacherData.username);
        await page.fill('#fullname', teacherData.fullname);
        await page.fill('#email', teacherData.email);
        await page.fill('#phone_number', teacherData.phone);
        await page.fill('#password', teacherData.password);
        await page.fill('#confirm_password', teacherData.password);
        await page.setInputFiles('#proof_file', pdfPath);
        await page.click('#signup-btn');
        await expect(page).toHaveURL(/teacher\/login/);

        // --- Approve ---
        await page.goto('/customadmin/portal-secure-access/');
        await page.fill('input[name="username"]', adminData.username);
        await page.fill('input[name="password"]', adminData.password);
        await page.click('button[type="submit"]');
        await page.goto('/customadmin/pending/teachers/');
        await page.evaluate((uname) => {
            const row = Array.from(document.querySelectorAll('tr')).find(r => r.innerText.includes(uname));
            if (row) {
                const btn = Array.from(row.querySelectorAll('a')).find(a => a.innerText.toLowerCase().includes('approve')) as HTMLAnchorElement;
                if (btn) {
                    const onclick = btn.getAttribute('onclick');
                    if (onclick) {
                        const m = onclick.match(/window\.location\.href\s*=\s*'([^']+)'/);
                        if (m) window.location.href = m[1];
                    } else if (btn.href && !btn.href.includes('javascript')) {
                        window.location.href = btn.href;
                    }
                }
            }
        }, teacherData.username);
        await page.waitForLoadState('networkidle');

        // --- First Login ---
        await context.clearCookies();
        await page.goto('/teacher/login/');
        await page.fill('#username', teacherData.username);
        await page.fill('#password', teacherData.password);
        await page.click('#loginBtn');

        await page.waitForURL(/\/teacher\/profile\/edit/);
        console.log('[DEBUG] On Profile Page (Teacher)');

        const avatars = page.locator('.avatar-option');
        const count = await avatars.count();
        if (count > 0) {
            await page.evaluate(() => {
                const el = document.querySelector('.avatar-option') as HTMLElement;
                if (el) el.click();
            });
        }

        await page.waitForTimeout(2000);
        await page.screenshot({ path: 'screenshots/verify_teacher_selection.png' });

        console.log('[ACTION] Submitting Teacher Profile...');
        await page.click('#avatarSubmitBtn');

        await page.waitForTimeout(5000);
        if (page.url().includes('/teacher/dashboard')) {
            console.log('[RESULT] TEACHER SUCCESS reached dashboard');
        } else {
            console.log(`[RESULT] TEACHER FAILED at ${page.url()}`);
        }
    });
});
