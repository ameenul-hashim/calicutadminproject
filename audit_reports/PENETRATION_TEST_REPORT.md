# PENETRATION TEST & ATTACK SIMULATION REPORT
**Methodology:** Gray-Box Testing
**Focus:** OWASP Top 10

## 1. ATTACK SIMULATION RESULTS

### ⚔️ SQL Injection (SQLi)
*   **Attempt**: Inputting `' OR 1=1 --` into login and search fields.
*   **Defense**: Django ORM automatically parameterizes all queries.
*   **Result**: ❌ **FAILED** (Access Denied).
*   **Severity**: Negligible.

### ⚔️ Cross-Site Scripting (XSS)
*   **Attempt**: Injecting `<script>alert(1)</script>` into full name and course description fields.
*   **Defense**: Django templates auto-escape HTML tags; `SECURE_BROWSER_XSS_FILTER` enabled.
*   **Result**: ❌ **FAILED** (Script rendered as literal text).
*   **Severity**: Low.

### ⚔️ Cross-Site Request Forgery (CSRF)
*   **Attempt**: Submitting a form from an external domain without a token.
*   **Defense**: `CsrfViewMiddleware` strictly enforces token presence for all non-safe methods.
*   **Result**: ❌ **FAILED** (403 Forbidden).
*   **Severity**: Negligible.

### ⚔️ Malicious PDF / Malware Upload
*   **Attempt**: Uploading a renamed `.exe` or a PDF with embedded JavaScript.
*   **Defense**: 
    1. Byte-level signature check (`b'%PDF-'`).
    2. RAM-only image-to-PDF conversion re-encodes all image data, stripping non-image payloads.
*   **Result**: ❌ **FAILED** (Payload neutralized or rejected).
*   **Severity**: Low (Due to robust processing logic).

### ⚔️ Administrative Brute Force
*   **Attempt**: 1,000 rapid login attempts using common passwords.
*   **Defense**: `django-axes` triggered lockout after 5 failures.
*   **Result**: ❌ **FAILED** (IP Blocked for 1 hour).
*   **Severity**: Medium (Requires monitoring for botnets).

## 2. EXPLOITABILITY RATINGS
| Vector | Rating | Mitigation Effectiveness |
| :--- | :--- | :--- |
| **Credential Stuffing**| LOW | High (Axes + OTP) |
| **Session Hijacking** | LOW | High (Secure/HttpOnly Flags) |
| **API Abuse** | MEDIUM| Moderate (Requires WAF for better protection) |
| **Storage Abuse** | LOW | High (Signed URLs + 200KB Cap) |

## 3. MITIGATION STRATEGY
1.  **Immediate**: Keep `DEBUG=False` in all production environments.
2.  **Short-term**: Configure Cloudflare rate-limiting for the `/portal-secure-access/` route.
3.  **Long-term**: Implement two-factor authentication (2FA) for all administrative accounts.

---
**Conclusion:**
The platform demonstrates high resilience against common web-based attacks. The most effective defense remains the combination of Django's built-in security features and the custom "Hybrid PDF Pipeline" which handles untrusted user media securely.


