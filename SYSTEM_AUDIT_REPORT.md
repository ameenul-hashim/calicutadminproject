# Neo Learner SYSTEM AUDIT REPORT
**Date:** May 7, 2026
**Status:** PRODUCTION READY
**Platform:** [calicutadmin.onrender.com](https://calicutadmin.onrender.com)

---

## 1. INFRASTRUCTURE & STORAGE AUDIT
The application uses a distributed storage architecture to balance security and performance.

| Component | Provider | Purpose | Data Size (Avg) | Security |
| :--- | :--- | :--- | :--- | :--- |
| **Core Database** | Render PostgreSQL | Users, Courses, Records | 2KB - 10KB / record | SSL Encrypted |
| **Identity Proofs** | Supabase Storage | Sensitive Student/Teacher IDs | **Under 200KB** | Private / Signed URLs |
| **Course Media** | Cloudinary | Thumbnails & Lesson Videos | Managed by Cloudinary | Public CDN |
| **Real-time / Cache**| Redis | Chat & Analytics Cache | Transient (RAM) | Internal VPC |

---

## 2. SECURITY & DATA PRIVACY
### 🛡️ Core Security Layers
*   **Brute-Force Protection**: Integrated `django-axes` to lock accounts after 5 failed attempts (1-hour cooldown).
*   **Secure Recovery**: OTP-based password reset with a strict **5-minute expiry** window and complexity validation.
*   **Environment Safety**: Verified `.env` and `credentials.json` are in `.gitignore`. **No secrets are exposed in the repository.**
*   **Role Isolation**: Strict separation between Admin, Teacher, and Student views. Admins cannot be bypassed via URL manipulation.

### 🔐 Document Privacy
*   Identity documents are stored in a **private Supabase bucket**.
*   Documents are never accessed via direct links; they use **Signed URLs** that expire automatically after 1 hour.

---

## 3. MOBILE REGISTRATION PIPELINE (IMAGE-TO-PDF)
The system features a custom-built, RAM-optimized conversion engine to handle mobile uploads.

**Working Flow:**
1.  **Detection**: Detects if the upload is an image (`.jpg`, `.png`, `.heic`).
2.  **RAM Processing**: The image is processed entirely in memory (no slow temporary files).
3.  **Adaptive Compression**:
    *   Intelligently resizes to **1200px** width.
    *   Strips EXIF metadata (Privacy).
    *   Adjusts JPEG quality iteratively until the file is **< 200KB**.
4.  **PDF Generation**: Uses `ReportLab` to wrap the optimized image in a professional A4 PDF.
5.  **Supabase Sync**: Uploads the final PDF directly to Supabase.

---

## 4. OPERATIONAL WORKFLOWS
### 👨‍💼 Admin Flow
*   **Dashboard**: Real-time analytics (refreshed every 60s).
*   **Approval**: Multi-step verification for Teachers and Students.
*   **Content**: Granular approval/rejection for individual lessons and courses.

### 👨‍🏫 Teacher Flow
*   **CrNLion**: Course builder with thumbnail optimization.
*   **Revenue**: Automated reporting and profile management.
*   **Preview**: "Student View" mode with a "Back to Teacher Panel" safety toggle.

### 🎓 Student Flow
*   **Learning**: Side-by-side Course Player with persistent sidebar.
*   **Security**: Verification required before any course access.

---

## 5. DATA CONSISTENCY CHECK
*   **Integrity**: Uses Django `transaction.atomic()` for critical operations (like signup) to ensure no "half-created" users exist if a file upload fails.
*   **Cleanup**: Automatic deletion of files from Supabase/Cloudinary when a course or user is rejected/deleted.
*   **Stability**: No `Internal Server Error (500)` detected in core flows; all inputs are validated for length and format (e.g., 10-digit phone numbers).

---
**Audit Conclusion:**
The application is highly optimized for mobile-first regions while maintaining enterprise-grade security for sensitive documents. Storage usage is efficiently capped to keep operation costs low and system performance high.



