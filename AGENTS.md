# AGENTS.md — Neo Learner E-Learning Platform
# Master AI Reference Document
# Last Updated: 2026-06-06 | Branch: 3-fullcorrect

---

## 🎯 PROJECT IDENTITY

| Field | Value |
|:---|:---|
| **Project Name** | Neo Learner (Calicut Admin) |
| **Type** | Multi-role E-Learning Platform |
| **Framework** | Django 5.1.1 + Django Channels (ASGI) |
| **Python** | 3.x (Render runtime) |
| **Primary Language** | Python (backend), HTML/CSS/JS (frontend, no SPA framework) |
| **Database (Prod)** | PostgreSQL via Supabase (via `DATABASE_URL`) |
| **Database (Dev)** | SQLite3 (`db.sqlite3`) |
| **Auth Model** | `accounts.CustomUser` (AbstractUser extension) |
| **GitHub Repo** | https://github.com/ameenul-hashim/calicutadminproject |
| **Production URL** | https://neolearner.onrender.com |
| **Admin Portal** | https://calicutadmin.onrender.com |
| **Legacy URL** | https://edustreamcalicut.onrender.com |

---

## 🌿 GIT BRANCH STRUCTURE

### Active Branches

| Branch | Purpose | Status |
|:---|:---|:---|
| `ongoing` | **PRIMARY development branch** — all active work happens here | ✅ HEAD |
| `stable-may19-rollback` | Stable rollback point (May 19 state) | 🔒 Frozen |

### Remote: `origin`
```
https://github.com/ameenul-hashim/calicutadminproject.git
```

### Branch Rules
- **Always work on `ongoing`** — this is the only active development branch.
- **Never push directly to `stable-may19-rollback`** — it is a safety snapshot.
- Deploy to Render triggers from `ongoing` pushes via GitHub auto-deploy.
- Emergency rollback = Render manual deploy pinned to `stable-may19-rollback`.

### Recent Git History (last meaningful commits)
- `bcf2163` — Final encoding fix for requirements (2026-05-31)
- `ba23686` — Implemented resource deletion workflow (2026-05-29)

---

## 🏗️ PROJECT STRUCTURE

```
e-learning application/
├── manage.py
├── requirements.txt          ← pip dependencies
├── build.sh                  ← Render build script (pip + collectstatic + migrate)
├── runtime.txt               ← Python version for Render
├── .env                      ← Local env vars (never commit)
├── .gitignore
├── AGENTS.md                 ← THIS FILE
├── db.sqlite3                ← Dev-only SQLite
├── security.log              ← Django security event log
│
├── elearning_project/        ← Django project config
│   ├── settings.py           ← Main settings (env-driven)
│   ├── urls.py               ← Root URL conf
│   ├── asgi.py               ← ASGI + WebSocket (Daphne)
│   └── wsgi.py
│
├── accounts/                 ← MAIN APP (students, teachers, courses, resources)
│   ├── models.py             ← ALL 13 models defined here
│   ├── views.py              ← ~95KB — teacher, student, and shared views
│   ├── urls.py               ← 54 URL patterns (no prefix)
│   ├── consumers.py          ← WebSocket consumer (real-time chat)
│   ├── routing.py            ← WebSocket URL routing
│   ├── middleware.py         ← PortalSecurityMiddleware + EnterpriseHardeningMiddleware
│   ├── context_processors.py ← pending_counts (global context)
│   ├── admin.py
│   └── utils/
│       ├── supabase_storage.py   ← Signed URL generation, PDF upload/delete
│       ├── storage_manager.py    ← StorageManager class (Supabase + Firebase bridge)
│       ├── cloudinary_helpers.py ← Image upload/delete helper
│       ├── otp_engine.py         ← OTP generation, hashing, verification
│       ├── pdf_processor.py      ← PDF compression (PyMuPDF/ReportLab)
│       ├── pdf_helpers.py
│       ├── malware_scanner.py    ← File type/MIME validation
│       ├── totp_service.py       ← TOTP 2FA service
│       ├── keep_alive.py         ← Render spin-down prevention
│       ├── billing_safety.py
│       └── recovery_sim.py
│
├── custom_admin/             ← ADMIN PORTAL APP
│   ├── models.py             ← Empty (uses accounts models)
│   ├── views.py              ← ~81KB — all admin-facing views
│   ├── urls.py               ← 58 URL patterns (prefix: customadmin/)
│   └── templates/custom_admin/
│
├── core/                     ← Shared utilities (minimal)
├── static/                   ← CSS, JS, images (WhiteNoise served)
├── media/                    ← Dev media (Cloudinary in prod)
└── scratch/                  ← Temp/debug scripts
```

---

## 🗄️ DATA MODELS (accounts/models.py)

### 1. `CustomUser` (AbstractUser)
The single user model for all roles.

| Field | Type | Notes |
|:---|:---|:---|
| `user_type` | CharField | ADMIN / TEACHER / STUDENT |
| `status` | CharField | PENDING / ACTIVE / BLOCKED / REJECTED |
| `full_name` | CharField | Display name |
| `image` | URLField | Cloudinary URL (primary avatar) |
| `image_public_id` | CharField | Cloudinary delete key |
| `pdf_path` | CharField | **Supabase storage path** (primary proof PDF) |
| `pdf_url` | URLField | Legacy Cloudinary URL (fallback) |
| `proof_pdf` | CharField | Legacy Supabase path (deprecated) |
| `phone_number` | CharField | Indexed |
| `rejection_reason` | TextField | Admin rejection message |
| `approved_by` | FK(self) | Admin who approved |
| `approved_at` | DateTimeField | |
| `current_session_key` | CharField | Single-session enforcement |
| `uid` | UUIDField | Public-facing unique ID (indexed) |
| `totp_secret` | CharField | TOTP 2FA secret |

**Properties:** `avatar_url` (Cloudinary → ui-avatars fallback), `proof_pdf_url` (Supabase signed URL)

### 2. `Course`
| Field | Notes |
|:---|:---|
| `teacher` → CustomUser | Owner |
| `status` | DRAFT / PENDING / PUBLISHED / REJECTED / DELETED |
| `image` / `image_public_id` | Cloudinary thumbnail |
| `uid` | UUID routing key |
| `has_pending_edits` | Teacher edit-resubmission workflow flag |
| `pending_*` fields | Staged edits awaiting admin approval |

### 3. `Lesson`
- Belongs to Course
- Has `video_url` (YouTube) or `video_file` (upload)
- Full pending-edit workflow (`pending_*` fields, `has_pending_edits`)
- `status`: PENDING / APPROVED / REJECTED

### 4. `CourseResource`
The most complex model — handles teacher-uploaded study materials.

| Field | Notes |
|:---|:---|
| `category` | ENGLISH / MALAYALAM / ONLINE |
| `resource_type` | PDF / DOCX / PPTX / XLSX / TXT |
| `firebase_file_path` | **Primary storage path** (Supabase, despite field name) |
| `backup_file_path` | Google Drive backup path |
| `backup_status` | PENDING / SUCCESS / FAILED |
| `thumbnail_path` | Cloudinary thumbnail path |
| `status` | PENDING / APPROVED / REJECTED / DELETION_PENDING |
| `is_deleted` | Soft-delete flag |
| `has_pending_edits` | Teacher resubmission flag |
| `view_count` / `download_count` | Analytics |
| `uid` | UUID routing key |

**Method:** `get_signed_url()` — generates 7-day Supabase signed URL

### 5. `Enrollment`
- `user` + `course` (unique_together)

### 6. `LiveClass`
- Meeting link + date_time per course

### 7. `ApprovalLog`
- Generic content_type + object_id log for all admin review actions

### 8. `Report`
- User-filed content reports (PENDING / REVIEWED / RESOLVED)

### 9. `Notification`
- Per-user, soft-delete via `is_read`, UUID keyed

### 10. `ChatMessage`
- Sender/receiver FK, `is_edited`, `is_deleted`, ordered by timestamp
- Powered by WebSocket consumer at `ws/chat/<uid>/`

### 11. `EmailOTP`
- Purposes: PASSWORD_RESET / EMAIL_VERIFICATION / USERNAME_RECOVERY / EMAIL_UPDATE / USERNAME_UPDATE
- `otp_hash` (bcrypt hashed), expires\_at, attempt\_count, IP logging

### 12. `DeletionRequest`
- Teacher → Admin approval pipeline for deleting Resources or Lessons
- `status`: PENDING / APPROVED / REJECTED
- Direct `resource` FK added for resource deletion (lesson uses generic `item_type/item_id`)

### 13. `PDFAccessLog`
- Audit log for every proof-PDF access (admin portal)

### 14. `LoginHistory`
- Per-user login audit (IP, device, timestamp, status)

### 15. `AdminActivityLog`
- All admin actions logged with target user + details

### 16. `UploadJob`
- Tracks YouTube resumable upload state per teacher
- `status`: PENDING / UPLOADING / PROCESSING / COMPLETED / FAILED
- `progress_percentage` — server-side persistent progress (updated by browser via `POST /api/youtube/upload/<uid>/progress/`)
- `youtube_upload_url` — the resumable upload session URL
- `youtube_video_id` / `youtube_url` — final result after verification
- `error_message` — specific failure reason
- Linked to `teacher` (fk CustomUser) and optionally `lesson` (fk Lesson)
- Created by `init_youtube_upload`, finalized by `complete_youtube_upload`

### Signals (pre_delete)
- `CustomUser` → Cloudinary image cleanup + Supabase PDF delete
- `Course` → Cloudinary thumbnail cleanup (including pending_image)
- `Lesson` → video_file cleanup

---

## 🌐 URL ROUTING

### Root (`elearning_project/urls.py`)
```
/admin/          → Django admin
/                → accounts.urls (no prefix)
/customadmin/    → custom_admin.urls
```

### accounts/urls.py (57 patterns — NO prefix)
```
/                          → login_view (home)
/signup/                   → signup_view
/login/                    → login_view
/health/                   → health_check
/status/                   → status_page
/logout/                   → logout_view

# Teacher
/teacher/signup/           → teacher_signup_view
/teacher/login/            → teacher_login_view
/teacher/dashboard/        → teacher_dashboard
/teacher/courses/          → my_courses
/teacher/analytics/        → teacher_analytics_view
/teacher/explore/          → explore_courses
/teacher/courses/create/   → create_course
/teacher/courses/<uid>/edit/     → edit_course
/teacher/courses/<uid>/delete/   → delete_course
/teacher/courses/<uid>/lessons/  → course_lessons
/teacher/courses/<uid>/lessons/add/ → add_lesson
/teacher/courses/<uid>/submit/   → submit_course_approval
/teacher/courses/view/<uid>/     → view_other_course
/teacher/lessons/<uid>/edit/     → edit_lesson
/teacher/lessons/<uid>/delete/   → delete_lesson

# Resources
/course/<uid>/resource/add/      → add_resource
/resource/<uid>/edit/            → edit_resource
/resource/<uid>/delete/          → delete_resource
/resource/<uid>/access/          → access_resource (PDF viewer — X-Frame-Options exempted)
/resource/<uid>/download/        → download_resource

# Student
/student/enroll/<uid>/    → enroll_course
/student/explore/         → student_explore
/course/<uid>/play/       → course_player

# Shared
/dashboard/               → dashboard_view
/profile/                 → profile_view
/profile/edit/            → edit_profile

# Chat (REST + WebSocket)
/chat/send/               → send_chat_message
/chat/messages/<uid>/     → get_chat_messages
/chat/list/               → get_chat_list
ws/chat/<uid>/            → ChatConsumer (WebSocket)

# Notifications
/notifications/           → all_notifications
/notification/<uid>/read/ → mark_notification_read
/notification/<uid>/delete/ → delete_notification
/notifications/read-all/  → mark_all_notifications_read
/unread-counts/           → get_unread_counts

# YouTube Upload API
/api/youtube/init-upload/                         → init_youtube_upload (create UploadJob + session URL)
/api/youtube/upload/<uid>/progress/               → update_upload_progress (browser reports %)
/api/youtube/upload/<uid>/complete/               → complete_youtube_upload (verify + finalize)
/api/youtube/upload/<uid>/status/                 → get_upload_status (poll for refresh persistence)

# Auth flows
/forgot-password/         → forgot_password
/recover-username/        → recover_username
/verify-otp/              → verify_otp
/reset-password/          → reset_password

# Auth bridge (Admin impersonation)
/student-view/auth/       → student_view_auth
/teacher-view/auth/       → teacher_view_auth
```

### custom_admin/urls.py (58 patterns — prefix: /customadmin/)
```
/customadmin/portal-secure-access/  → admin_login_view (hidden URL)
/customadmin/dashboard/             → admin_dashboard
/customadmin/students/              → manage_students
/customadmin/teachers/              → manage_teachers
/customadmin/analytics/             → analytics_view
/customadmin/storage-dashboard/     → storage_dashboard
/customadmin/enterprise-monitor/    → enterprise_monitor
/customadmin/system-audit/          → system_audit_view
/customadmin/master-audit-summary/  → master_audit_summary_view

# Pending approvals
/customadmin/pending/               → pending_users_view
/customadmin/pending/teachers/      → pending_teachers_view
/customadmin/pending/resources/     → pending_resources
/customadmin/pending/courses/       → pending_courses_view

# Course actions
/customadmin/course/approve/<uid>/  → approve_course
/customadmin/course/reject/<uid>/   → reject_course
/customadmin/course/<uid>/verify/   → admin_view_course_content
/customadmin/course/delete/secure/<uid>/   → admin_delete_course_secure
/customadmin/course/permanent-delete/secure/<uid>/ → admin_permanent_delete_course_secure
/customadmin/course/restore/<uid>/  → admin_restore_course
/customadmin/deleted-courses/       → deleted_courses_view

# Lesson actions
/customadmin/lesson/approve/<uid>/  → approve_lesson
/customadmin/lesson/reject/<uid>/   → reject_lesson
/customadmin/lesson/delete/secure/<uid>/  → admin_delete_lesson_secure

# Resource actions
/customadmin/resource/approve/<uid>/  → approve_resource
/customadmin/resource/reject/<uid>/   → reject_resource

# User management
/customadmin/user/accept/<uid>/     → accept_user
/customadmin/user/decline/<uid>/    → decline_user
/customadmin/user/toggle/<uid>/     → toggle_user_status
/customadmin/user/edit/<uid>/       → edit_user_admin
/customadmin/user/delete/<uid>/     → delete_user_admin
/customadmin/student/create/        → create_student_admin
/customadmin/student/<uid>/profile/ → admin_student_profile
/customadmin/teacher/create/        → create_teacher_admin
/customadmin/teacher/<uid>/profile/ → admin_teacher_profile
/customadmin/student-view/auth/     → admin_student_view_auth (impersonation)

# Deletion requests
/customadmin/deletion-requests/                     → manage_deletion_requests
/customadmin/deletion-requests/<uid>/verify/        → verify_deletion_request
/customadmin/deletion-requests/<uid>/approve/       → approve_deletion_request
/customadmin/deletion-requests/<uid>/reject/        → reject_deletion_request

# Other
/customadmin/notifications/         → admin_all_notifications
/customadmin/secure-pdf-access/<uid>/ → proxy_pdf_access
/customadmin/content/               → content_management_view
```

### Error Handlers
```python
handler404 = 'custom_admin.views.error_404'
handler500 = 'custom_admin.views.error_500'
```

---

## ⚙️ SETTINGS OVERVIEW

### Key Settings
| Setting | Value |
|:---|:---|
| `AUTH_USER_MODEL` | `accounts.CustomUser` |
| `ROOT_URLCONF` | `elearning_project.urls` |
| `ASGI_APPLICATION` | `elearning_project.asgi.application` |
| `SESSION_COOKIE_AGE` | 10800 (3 hours — for mobile student persistence) |
| `SESSION_COOKIE_NAME` | `neolearner_sessionid` |
| `CSRF_USE_SESSIONS` | True (session-based CSRF) |
| `X_FRAME_OPTIONS` | `DENY` (prod) — **exempted for `/resource/<uid>/access/`** |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | 10 MB |
| `DEFAULT_STORAGE` | `cloudinary_storage.storage.MediaCloudinaryStorage` |
| `STATICFILES_STORAGE` | `whitenoise.storage.CompressedManifestStaticFilesStorage` |
| `AXES_FAILURE_LIMIT` | 5 (brute-force lockout) |
| `AXES_COOLOFF_TIME` | 1 hour |

### Environment Variables Required
```bash
# Core
SECRET_KEY=
DEBUG=False
DATABASE_URL=            # PostgreSQL (Supabase)
ALLOWED_HOSTS=           # comma-separated
CSRF_TRUSTED_ORIGINS=    # comma-separated

# Cloudinary (Profile photos, course thumbnails, resource thumbnails)
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=

# Supabase (Primary file storage: PDFs, resources)
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_BUCKET=

# Redis (WebSocket + Cache — optional, falls back to in-memory)
REDIS_URL=

# Email (SMTP for OTP emails)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=

# YouTube Data API (Teacher video upload)
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=

# Sentry (optional but recommended)
SENTRY_DSN=

# Google Drive (backup storage)
GOOGLE_DRIVE_CREDENTIALS=  # JSON credential
```

---

## 📦 TECH STACK & DEPENDENCIES

### Backend
| Package | Version | Purpose |
|:---|:---|:---|
| Django | 5.1.1 | Web framework |
| channels | 4.3.2 | WebSocket / ASGI |
| daphne | 4.2.1 | ASGI server |
| channels-redis | 4.2.1 | Redis channel layer |
| gunicorn | 23.0.0 | WSGI fallback |
| psycopg2 | 2.9.9 | PostgreSQL driver |
| dj-database-url | 2.3.0 | DATABASE_URL parser |
| supabase | 1.2.0 | Storage (PDFs, resources) |
| cloudinary | 1.44.2 | Image hosting |
| django-cloudinary-storage | 0.3.0 | Django storage backend |
| whitenoise | 6.7.0 | Static file serving |
| sentry-sdk | 2.13.0 | Error monitoring |
| django-axes | 6.5.0 | Brute-force protection |
| django-ratelimit | 4.1.0 | Rate limiting |
| django-cleanup | 9.0.0 | Auto file cleanup on delete |
| python-magic | 0.4.27 | MIME type detection |
| PyMuPDF | 1.24.4 | PDF processing |
| reportlab | 4.5.0 | PDF generation |
| firebase-admin | 6.5.0 | Firebase (legacy storage) |
| google-api-python-client | latest | Google Drive backup |
| Pillow | ≥11.1.0 | Image processing |
| pillow-heif | 1.3.0 | HEIF image support |
| python-dotenv | 1.0.1 | .env file loading |
| redis | 5.0.8 | Cache/sessions |
| pydantic | 2.13.3 | Supabase validation |

---

## 🔄 KEY WORKFLOWS

### 0. YouTube Resumable Upload Flow (Teacher Video)
```
Teacher selects MP4 → clicks "Add Lesson"
→ Browser POSTs /api/youtube/init-upload/ → UploadJob created (status=UPLOADING)
→ Server creates YouTube resumable upload session → returns {upload_url, job_uid}
→ Browser PUTs file directly to YouTube (zero server RAM/bandwidth)
→ Every ~5% progress, browser POSTs to /api/youtube/upload/<job_uid>/progress/
→ On upload completion, browser POSTs to /api/youtube/upload/<job_uid>/complete/
→ complete_youtube_upload calls verify_youtube_video() using YouTube Data API
→ If verified → UploadJob.status = COMPLETED, lesson youtube fields set
→ If not verified → UploadJob.status = FAILED, error_message populated
→ Form submits normally with YouTube URL → Lesson created with youtube_video_id
→ UploadJob.lesson linked to created Lesson
→ Refresh-safe: /api/youtube/upload/<job_uid>/status/ returns current progress
```

### 1. Teacher Resource Upload Flow
```
Teacher uploads PDF → malware_scanner validates MIME
→ pdf_processor compresses → Firebase/Supabase storage
→ CourseResource created (status=PENDING)
→ Admin notified → Admin reviews at /customadmin/pending/resources/
→ Admin approves → status=APPROVED, is_approved=True
→ Students can access via /resource/<uid>/access/
→ Google Drive backup triggered (backup_status tracked)
```

### 2. Teacher Edit/Resubmission Flow
```
Teacher edits approved resource → pending_* fields populated
→ has_pending_edits=True → Admin sees changes in pending queue
→ Admin approves → live fields updated, pending_* cleared
→ Admin rejects → pending_* cleared, teacher notified
```

### 3. Resource Deletion Flow
```
Teacher requests deletion → DeletionRequest created (status=PENDING)
→ CourseResource.status = DELETION_PENDING
→ Admin reviews at /customadmin/deletion-requests/<uid>/verify/
→ Admin approves → Supabase file deleted + CourseResource soft-deleted
→ Admin rejects → status reverts to APPROVED
```

### 4. User Registration Flow
```
Teacher: Signs up → status=PENDING → Admin approves at /customadmin/pending/teachers/
Student: Signs up → status=ACTIVE immediately (no manual approval needed)
Admin: Created only via Django admin or direct DB
```

### 5. Real-time Chat Flow
```
WebSocket connects to ws/chat/<other_user_uid>/
→ ChatConsumer groups by sorted(sender_uid, receiver_uid)
→ Messages saved to ChatMessage model
→ Admin identity masked (displayed as "Support Team" to students)
```

### 6. OTP / Auth Recovery Flow
```
/forgot-password/ → EmailOTP created (purpose=PASSWORD_RESET)
→ /verify-otp/ → OTP hash verified, session token granted
→ /reset-password/ → Password updated
Same flow for: EMAIL_VERIFICATION, USERNAME_RECOVERY, EMAIL_UPDATE, USERNAME_UPDATE
```

---

## 🚀 DEPLOYMENT (Render)

### Platform: Render (render.com)
| Setting | Value |
|:---|:---|
| **Service Type** | Web Service |
| **Build Command** | `./build.sh` (pip install + collectstatic + migrate) |
| **Start Command** | `daphne -b 0.0.0.0 -p $PORT elearning_project.asgi:application` |
| **Auto-Deploy** | Yes — triggers on push to `ongoing` branch |
| **Runtime** | Python 3.x (see `runtime.txt`) |

### build.sh
```bash
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
```

### Render URLs (Hardcoded in settings)
- `edustreamcalicut.onrender.com` — legacy
- `neolearner.onrender.com` — primary student portal
- `calicutadmin.onrender.com` — admin portal

---

## 🛡️ SECURITY

| Feature | Implementation |
|:---|:---|
| Brute-force protection | django-axes (5 attempts, 1hr lockout) |
| Rate limiting | django-ratelimit on auth endpoints |
| File validation | python-magic MIME check + extension whitelist |
| CSRF | Session-based (`CSRF_USE_SESSIONS=True`) |
| Session | DB-backed, 3hr for students, browser-close for admin/teacher |
| HSTS | Enabled in production (31536000s) |
| XSS | `SECURE_BROWSER_XSS_FILTER=True` |
| Clickjacking | `X_FRAME_OPTIONS='DENY'` (exempted for PDF viewer) |
| Error monitoring | Sentry SDK |
| Custom middleware | `PortalSecurityMiddleware`, `EnterpriseHardeningMiddleware` |
| Login history | `LoginHistory` model logs every login with IP/device |
| Admin activity | `AdminActivityLog` tracks all admin actions |
| PDF access log | `PDFAccessLog` logs every sensitive PDF access |

---

## 📊 STORAGE ARCHITECTURE

```
Images (avatars, thumbnails) → Cloudinary
    → Upload via cloudinary_helpers.py
    → URL stored in: CustomUser.image, Course.image, CourseResource.thumbnail_path
    → Delete via pre_delete signals

Documents (PDFs, DOCX etc.) → Supabase Storage
    → Upload via supabase_storage.py / storage_manager.py
    → Path stored in: CourseResource.firebase_file_path (misnomer — IS Supabase)
    → Access via 7-day signed URLs: CourseResource.get_signed_url()
    → Naming convention: courses/<course_uid>/resources/<uid>.<ext>

Proof PDFs (teacher credentials) → Supabase
    → Path stored in: CustomUser.pdf_path
    → Access via: CustomUser.proof_pdf_url property

Google Drive → Backup storage for approved resources
    → Tracked via CourseResource.backup_file_path + backup_status
```

---

## 🧩 AI TASK RULES

When working on this project, any AI should follow these rules:

### ✅ Always Do
1. **Use `uid` (UUID) for all URL routing** — never integer PKs in public URLs
2. **Check `has_pending_edits` flag** before modifying approved content
3. **Use `get_signed_url()`** for resource file access — never expose raw storage paths
4. **Run `python manage.py makemigrations accounts`** after any model changes
5. **Test on `ongoing` branch** — never work on `stable-may19-rollback`
6. **Add CSRF token** to all POST forms: `{% csrf_token %}`
7. **Check user type** (`request.user.user_type`) for role-based access control

### ❌ Never Do
1. Never hardcode Supabase/Cloudinary API keys — always use `os.getenv()`
2. Never expose `firebase_file_path`/`pdf_path` directly to templates
3. Never skip the `DeletionRequest` workflow for resource deletes
4. Never set `DEBUG=True` in production
5. Never add `X_FRAME_OPTIONS = 'ALLOWALL'` globally — only exempt specific views
6. Never commit `.env` or `db.sqlite3` to git

### Common Gotchas
- `CourseResource.firebase_file_path` = Supabase path (misleading field name from migration history)
- Admin login URL is hidden: `/customadmin/portal-secure-access/` (not `/customadmin/login/`)
- Chat admin identity is masked — `sender.user_type == 'ADMIN'` → display as "Support Team"
- `pdf_path` (new) vs `proof_pdf` (legacy deprecated) — always use `pdf_path`
- `SESSION_COOKIE_AGE = 10800` (3hr) applies only to students; admin/teacher use `session.set_expiry(0)`

---

## 📁 TEMPLATE LOCATIONS

```
accounts/templates/accounts/        ← Student + teacher templates
custom_admin/templates/custom_admin/ ← Admin portal templates
```

Key templates:
- `accounts/templates/accounts/dashboard.html` — Student dashboard
- `accounts/templates/accounts/teacher_dashboard.html` — Teacher dashboard
- `accounts/templates/accounts/course_player.html` — Student course player (mobile-optimized)
- `accounts/templates/accounts/profile.html` — User profile page
- `custom_admin/templates/custom_admin/dashboard.html` — Admin dashboard
- `custom_admin/templates/custom_admin/analytics.html` — Analytics dashboard
- `custom_admin/templates/custom_admin/decline_reason.html` — Rejection reason modal

---

## 🔍 CONTEXT PROCESSOR

`accounts/context_processors.py` — `pending_counts`
Available globally in all templates:
- `pending_user_count` — users awaiting approval
- `pending_course_count` — courses awaiting approval
- `pending_resource_count` — resources awaiting approval
- `pending_deletion_count` — deletion requests pending

---

## ⏰ RECOMMENDED CRON JOBS (Render)

| Command | Frequency | Purpose |
|:---|:---|:---|
| `python manage.py recover_orphaned_lessons --minutes-back 30` | Every 10 minutes | Recover lessons where YouTube upload succeeded but callback never fired (browser disconnect, timeout, etc.) |
| `python manage.py keep_alive` | Every 10 minutes | Prevent Render free-tier spin-down (if `keep_alive` management command exists) |

**Note:** Render does not natively support cron jobs. Use an external uptime monitor (e.g., cron-job.org, UptimeRobot, Better Uptime) that hits:
- `https://neolearner.onrender.com/health/` every 10 min (keep-alive + recovery check)
- Or deploy a tiny cron service container on the same Render project.

---

*This document is the single source of truth for any AI working on Neo Learner.*
*Updated: 2026-06-06. Maintain this file whenever models, URLs, or workflows change.*
