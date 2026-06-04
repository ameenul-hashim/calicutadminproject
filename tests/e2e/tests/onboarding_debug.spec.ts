import { test, expect } from '../helpers/test-utils';
import path from 'path';

/**
 * NeoLearn Business Workflow Audit - DEBUG MODE
 * Focus: Ensuring Onboarding (Avatar Selection) works and transitions correctly.
 */

test.describe('NeoLearn Onboarding Debug', () => {
    const timestamp = Date.now();
    const prefix = `debug_${timestamp}`;
    const testData = {
        teacher: {
            username: `${prefix}_t`,
            fullname: `Debug Teacher`,
            email: `${prefix}_t@example.com`,
            phone: `9${timestamp.toString().slice(-9)}`,
            password: 'StrongPassword123!'
        },
        admin: {
            username: 'hashim',
            password: 'Pkd02786*'
        }
    };

    test('Debug Onboarding Lifecycle', async ({ page, context }) => {
        const pdfPath = path.join(process.cwd(), 'test_resource.pdf');

        // 1. Signup Teacher
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

        // 2. Admin Approve
        await page.goto('/customadmin/portal-secure-access/');
        await page.fill('input[name="username"]', testData.admin.username);
        await page.fill('input[name="password"]', testData.admin.password);
        await page.click('button[type="submit"]');
        await page.goto('/customadmin/pending/teachers/');
        await page.evaluate((name) => {
            const row = Array.from(document.querySelectorAll('tr')).find(r => r.innerText.includes(name));
            if (row) {
                const btn = Array.from(row.querySelectorAll('a')).find(a => a.innerText.toLowerCase().includes('approve')) as HTMLAnchorElement;
                if (btn) {
                    const onclick = btn.getAttribute('onclick');
                    if (onclick) {
                        const m = onclick.match(/window\.location\.href\s*=\s*'([^']+)'/);
                        if (m) window.location.href = m[1];
                    } else {
                        btn.click();
                    }
                }
            }
        }, testData.teacher.username);
        await page.waitForLoadState('networkidle');

        // 3. Login Teacher
        await context.clearCookies();
        await page.goto('/teacher/login/');
        await page.fill('#username', testData.teacher.username);
        await page.fill('#password', testData.teacher.password);
        await page.click('#loginBtn');

        // 4. Handle Profile Redirect
        await page.waitForURL(/\/profile\/edit\//);
        console.log('[DEBUG] Landed on Profile Edit page.');
        await page.screenshot({ path: 'screenshots/debug_profile_land.png' });

        // WAIT for avatars to load
        const avatarOptions = page.locator('.avatar-option');
        await expect(avatarOptions.first()).toBeVisible();
        
        console.log('[DEBUG] Selecting first avatar...');
        // Click the first avatar option
        await avatarOptions.first().click();
        
        // Wait for the "selected" class to be added
        await expect(avatarOptions.first()).toHaveClass(/selected/);
        
        // Check if hidden input has value
        const hiddenValue = await page.getAttribute('#avatarUrlInput', 'value');
        console.log(`[DEBUG] Hidden Input Value: ${hiddenValue}`);
        
        await page.screenshot({ path: 'screenshots/debug_profile_selected.png' });

        // 5. Click Update
        console.log('[DEBUG] Clicking Update Profile...');
        await page.click('#submitBtn');

        // Capture response toast if any
        try {
            const toast = page.locator('.toast, .alert, #statusText');
            await expect(toast).toBeVisible({ timeout: 5000 });
            console.log(`[DEBUG] Toast/Status content: ${await toast.innerText()}`);
        } catch (e) {
            console.log('[DEBUG] No toast visible immediately.');
        }

        // Wait for redirect to dashboard
        await page.waitForURL(/\/teacher\/dashboard/, { timeout: 30000 });
        console.log('[DEBUG] Successfully reached Teacher Dashboard.');
        await page.screenshot({ path: 'screenshots/debug_dashboard_reached.png' });
    });
});
