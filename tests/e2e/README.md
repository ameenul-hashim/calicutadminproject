# NeoLearn LMS Master E2E Test Suite

This suite uses **Playwright** to perform comprehensive end-to-end testing of the NeoLearn LMS, covering Student, Teacher, and Admin workflows.

## 🚀 Quick Start

1. **Navigate to the test directory**:
   ```bash
   cd "tests/e2e"
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Install Playwright Browsers**:
   ```bash
   npx playwright install chromium
   ```

4. **Run the Master Suite** (Headed mode with SlowMo for visual tracking):
   ```bash
   npm run test
   ```

## 📊 Reports & Artifacts

After execution, detailed reports are generated in:
- `playwright-report/`: Consolidated HTML report.
- `test-results/`: Contains screenshots (on failure), videos (all runs), and traces.
- `logs/`: Extracted console and network error logs for failed tests.

## 🧪 Included Tests

- **`master.spec.ts`**: Full lifecycle verification (Signup -> Admin Approval -> Course Creation -> Student Access).
- **`security.spec.ts`**: Role isolation, unauthorized access, and permission bypass checks.
- **`validation.spec.ts`**: Empty form submissions, invalid email formats, and file type restrictions.

## 🐛 Bug Report Format

When a test fails, the system automatically captures:
1. **Video Recording**: High-quality MP4 of the entire session.
2. **Failure Screenshot**: Exact state of the UI at the moment of failure.
3. **Trace View**: Step-by-step execution timeline with network requests.
4. **Console Logs**: All browser errors and warnings.
5. **Network Logs**: Detailed list of failed API calls or resource loads.

To report a bug, simply attach the folder for the failed test case from `test-results/`.
