const { expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'https://neolearner.onrender.com';
const ADMIN_PORTAL = `${BASE_URL}/customadmin/portal-secure-access/`;
const TEST_PDF = path.join(__dirname, 'test_resource.pdf');

const ADMIN_CREDENTIALS = {
  username: 'hashim',
  password: 'Pkd02786*',
};

function timestamp() {
  return Date.now().toString().slice(-8);
}

function createStudentCredentials() {
  const ts = timestamp();
  return {
    fullName: `Test Student ${ts}`,
    email: `student_${ts}@test.neolearner.com`,
    username: `student_${ts}`,
    password: 'TestPass123!',
    phone: `987654${ts.slice(0, 4)}`,
  };
}

function createTeacherCredentials() {
  const ts = timestamp();
  return {
    fullName: `Test Teacher ${ts}`,
    email: `teacher_${ts}@test.neolearner.com`,
    username: `teacher_${ts}`,
    password: 'TestPass123!',
    phone: `987654${ts.slice(0, 4)}`,

  };
}

async function navigateAndWait(page, url, options = {}) {
  try {
    const fullUrl = url.startsWith('/') ? `${BASE_URL}${url}` : url;
    await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: 30000, ...options });
    return true;
  } catch (e) {
    console.log(`Navigation timeout/error for ${url}: ${e.message}`);
    return false;
  }
}

async function waitForSelectorSafe(page, selector, timeout = 10000) {
  try {
    await page.waitForSelector(selector, { timeout });
    return true;
  } catch {
    return false;
  }
}

async function takeScreenshot(page, name) {
  try {
    await page.screenshot({ path: `test-results/screenshots/${name}_${Date.now()}.png`, fullPage: true });
  } catch (e) {
    console.log(`Screenshot failed for ${name}: ${e.message}`);
  }
}

async function logPageState(page, label) {
  try {
    const url = page.url();
    const title = await page.title();
    console.log(`[${label}] URL: ${url} | Title: ${title}`);
    return { url, title };
  } catch (e) {
    console.log(`[${label}] Error getting page state: ${e.message}`);
    return { url: 'unknown', title: 'unknown' };
  }
}

async function collectConsoleErrors(page) {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push({ type: 'console', text: msg.text() });
    }
  });
  page.on('pageerror', err => {
    errors.push({ type: 'page', text: err.message });
  });
  page.on('requestfailed', req => {
    errors.push({ type: 'network', url: req.url(), text: req.failure()?.errorText });
  });
  return errors;
}

async function tryClick(page, selector, options = {}) {
  try {
    await page.click(selector, options);
    return true;
  } catch (e) {
    console.log(`Click failed for "${selector}": ${e.message}`);
    return false;
  }
}

async function tryFill(page, selector, value) {
  try {
    await page.fill(selector, String(value));
    return true;
  } catch (e) {
    console.log(`Fill failed for "${selector}": ${e.message}`);
    return false;
  }
}

async function checkElementExists(page, selector) {
  try {
    return await page.locator(selector).count() > 0;
  } catch {
    return false;
  }
}

async function checkForJsErrors(page) {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  page.on('pageerror', err => {
    errors.push(err.message);
  });
  await page.evaluate(() => console.log('check'));
  await page.waitForTimeout(500);
  return errors;
}

function getTestPdfPath() {
  if (fs.existsSync(TEST_PDF)) {
    return TEST_PDF;
  }
  // Fallback: create a minimal PDF
  const fallback = path.join(__dirname, 'fallback_test.pdf');
  if (!fs.existsSync(fallback)) {
    const { execSync } = require('child_process');
    try {
      execSync(`python -c "from reportlab.pdfgen import canvas; c = canvas.Canvas('${fallback}'); c.drawString(100, 750, 'Test'); c.save()"`);
    } catch {
      // Write a minimal valid PDF
      fs.writeFileSync(fallback, '%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF');
    }
  }
  return fallback;
}

module.exports = {
  BASE_URL,
  ADMIN_PORTAL,
  ADMIN_CREDENTIALS,
  timestamp,
  createStudentCredentials,
  createTeacherCredentials,
  navigateAndWait,
  waitForSelectorSafe,
  takeScreenshot,
  logPageState,
  collectConsoleErrors,
  tryClick,
  tryFill,
  checkElementExists,
  checkForJsErrors,
  getTestPdfPath,
};
