# AGENTS.md — Neo Learner E-Learning Platform
# Master AI Reference Document
# Last Updated: 2026-06-13 | Branch: 3-fullcorrect

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

## 🌿 GIT BRANCH STRUCTURE — CRITICAL

### ⚠️ AI AGENT WORKS ONLY ON `3-fullcorrect` BRANCH
### ⚠️ NEVER CREATE, MERGE, SWITCH TO, OR MODIFY ANY OTHER BRANCH
### ⚠️ IF A TASK SAYS "MERGE" OR "SYNC" BRANCHES — IGNORE IT

| Branch | Purpose | Status |
|:---|:---|:---|
| `* 3-fullcorrect` | **AI agent work branch** — all fixes by AI go here | ✅ Active |
| `13-fullcorrect-copy` | Safety snapshot of `3-fullcorrect` (created 2026-06-13) | 🔒 Frozen |
| `04-attempt` | Old attempt | 🔒 Frozen |
| `12-june-fullcorrect` | Old attempt | 🔒 Frozen |
| `main` | Default branch (inactive) | 🔒 Frozen |
| `stable-may19-rollback` | Emergency rollback point (May 19 state) | 🔒 Frozen |

### Branch Rules — READ CAREFULLY
- **AI agent works ONLY on `3-fullcorrect` branch.**
- **NEVER switch to any other branch** — not even to look.
- **NEVER merge, sync, or reset branches.**
- **NEVER push to `stable-may19-rollback`** — it is a safety snapshot.
- **If an instruction says "switch to X branch" or "merge Y into Z"** — stop and ask for clarification.
- **`13-fullcorrect-copy`** is a safety snapshot of `3-fullcorrect`. If changes break the project, user will restore from this branch manually.
- Auto-deploy to Render triggers from `3-fullcorrect` pushes via GitHub.

### Current commit tip
```
e303d0f fix: use direct HTTP for Supabase bucket check/create (v2.16 API URL issue)
ab11d53 fix: remove manual creds.refresh(None) call causing 'NoneType not callable' error
c49c6ab feat: add OAuth2 personal Google Drive support (refresh token flow)
```

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
│   ├── models.py             ← ALL models defined here
│   ├── views.py              ← ~95KB — teacher, student, and shared views
│   ├── urls.py               ← 54 URL patterns (no prefix)
│   ├── consumers.py          ← WebSocket consumer (real-time chat)
│   ├── routing.py            ← WebSocket URL routing
│   ├── middleware.py         ← PortalSecurityMiddleware + EnterpriseHardeningMiddleware
│   ├── context_processors.py ← pending_counts (global context)
│   ├── admin.py
│   └── utils/
│       ├── supabase_storage.py      ← Signed URL generation, PDF upload/delete
│       ├── storage_manager.py       ← StorageManager class (Supabase + Firebase bridge)
│       ├── cloudinary_helpers.py    ← Image upload/delete helper
│       ├── google_drive_service.py  ← Google Drive API (OAuth + service account)
│       ├── drive_backup_service.py  ← Auto-router: Google Drive OAuth → MEGA fallback
│       ├── backup_trigger.py        ← Real-time backup functions (signup PDF, teacher resource)
│       ├── generate_drive_token.py  ← One-time OAuth token generator for Google Drive
│       ├── otp_engine.py            ← OTP generation, hashing, verification
│       ├── pdf_processor.py         ← PDF compression (PyMuPDF/ReportLab)
│       ├── pdf_helpers.py
│       ├── malware_scanner.py       ← File type/MIME validation
│       ├── totp_service.py          ← TOTP 2FA service
│       ├── keep_alive.py            ← Render spin-down prevention
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

### 5-15. Other Models
`Enrollment`, `LiveClass`, `ApprovalLog`, `Report`, `Notification`, `ChatMessage`, `EmailOTP`, `DeletionRequest`, `PDFAccessLog`, `LoginHistory`, `AdminActivityLog` — unchanged.

### 16. `UploadJob`
Tracks YouTube resumable upload state per teacher. Status: PENDING / UPLOADING / PROCESSING / COMPLETED / FAILED. Linked to `teacher` and optionally `lesson`.

### 17. `BackupLog`
Added for backup tracking (live DB restore + Drive uploads). Types: LIVE_DB, SIGNUP_PDF, TEACHER_RESOURCE, FULL_BACKUP.

### Signals (pre_delete)
- `CustomUser` → Cloudinary image cleanup + Supabase PDF delete
- `Course` → Cloudinary thumbnail cleanup (including pending_image)
- `Lesson` → video_file cleanup

### Signals (post_save)
- `CustomUser` (with pdf_path) → background thread: download PDF from Supabase → upload to Google Drive
- `CourseResource` (with firebase_file_path) → background thread: download from Supabase → upload to Google Drive

---

## 🌐 URL ROUTING

### Root (`elearning_project/urls.py`)
```
/admin/          → Django admin
/                → accounts.urls (no prefix)
/customadmin/    → custom_admin.urls
```

### accounts/urls.py (57 patterns — NO prefix)
Same as before. Key additions from backup work:
```
/customadmin/backup-center/                             → backup_center
/customadmin/backup-center/cron-trigger/                → backup_cron_trigger
/customadmin/backup-center/clear-activity/              → backup_clear_activity
```

### Accounts URL patterns (unchanged)
Full list in code at `accounts/urls.py`.

### custom_admin/urls.py (58 patterns — prefix: /customadmin/)
Full list in code at `custom_admin/urls.py`.

---

## ⚙️ SETTINGS OVERVIEW

### Key Settings (unchanged)
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
RESOURCE_SUPABASE_URL=
RESOURCE_SUPABASE_ANON_KEY=
RESOURCE_SUPABASE_SERVICE_ROLE_KEY=

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

# Sentry (optional)
SENTRY_DSN=

# Google Drive Backup (OAuth2 — personal Google account, 15GB free)
GOOGLE_DRIVE_CLIENT_ID=
GOOGLE_DRIVE_CLIENT_SECRET=
GOOGLE_DRIVE_REFRESH_TOKEN=

# Backup Supabase PostgreSQL (live DB standby — third Supabase instance)
BACKUP_DATABASE_URL=       # PostgreSQL URL for periodic primary→backup DB restore
BACKUP_SUPABASE_URL=       # Storage API URL for 3rd Supabase (DB dump storage)
BACKUP_SUPABASE_KEY=       # Service role key for 3rd Supabase storage
BACKUP_SUPABASE_BUCKET=    # Bucket name for DB backups on 3rd Supabase (default: backups)
BACKUP_CRON_TOKEN=         # Secret token for cron-job.org webhook

# Firebase (legacy — may be removable)
FIREBASE_SERVICE_ACCOUNT_PATH=
FIREBASE_RTDB_URL=

# Misc
DISABLE_AXES=True          # Dev only
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
| supabase | **2.16.0** | Storage (PDFs, resources) |
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
| google-api-python-client | **2.195.0** | Google Drive backup |
| google-auth-oauthlib | **1.3.1** | Google Drive OAuth2 |
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

### 1. Teacher Resource Upload Flow (Current — passes through Render RAM)
```
Teacher uploads PDF → Django receives file in RAM → Supabase Storage
→ CourseResource created (status=PENDING)
→ Signal fires → background thread downloads from Supabase → uploads to Google Drive
→ Admin notified → Admin reviews at /customadmin/pending/resources/
→ Admin approves → status=APPROVED
```

### 2. Signup PDF Upload Flow (Current — passes through Render RAM)
```
Student/Teacher uploads proof PDF → Django receives file in RAM → Supabase Storage
→ CustomUser.pdf_path saved
→ Signal fires → background thread downloads from Supabase → uploads to Google Drive
```

### 3. Backup Flow (Google Drive OAuth2)
```
Real-time (post_save signals):
  Signup PDF or teacher resource created
  → Background thread downloads file from Supabase
  → Uploads to Google Drive in folder:
    NeoLearner_Backups/Signup_Proofs/YYYY/MM/
    NeoLearner_Backups/Teacher_Resources/{Course}/{Chapter}/{Category}/

Daily cron (backup_daily_full):
  → pg_dump → .sql file
  → Uploads .sql to 3rd Supabase bucket (15-day retention)
  → (File collection + ZIP creation currently disabled — too RAM-heavy on Render 512MB)

Live DB restore (backup_to_live_db):
  → pg_dump from DATABASE_URL
  → psql restore to BACKUP_DATABASE_URL (third Supabase PostgreSQL)
  → Triggered every 4h via cron-job.org: ?type=supabase-db
```

### 4. Teacher Edit/Resubmission Flow (unchanged)
### 5. Resource Deletion Flow (unchanged)
### 6. User Registration Flow (unchanged)
### 7. Real-time Chat Flow (unchanged)
### 8. OTP / Auth Recovery Flow (unchanged)

---

## 🚀 DEPLOYMENT (Render)

| Setting | Value |
|:---|:---|
| **Service Type** | Web Service |
| **Build Command** | `./build.sh` (pip install + collectstatic + migrate) |
| **Start Command** | `daphne -b 0.0.0.0 -p $PORT elearning_project.asgi:application` |
| **Auto-Deploy** | Yes — triggers on push to `3-fullcorrect` branch |
| **Runtime** | Python 3.x (see `runtime.txt`) |

### build.sh
```bash
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
```

### Render URLs (Hardcoded in settings)
- `neolearner.onrender.com` — primary student portal
- `calicutadmin.onrender.com` — admin portal
- `edustreamcalicut.onrender.com` — legacy (redirects)

---

## 🛡️ SECURITY (unchanged)

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

Documents (PDFs, DOCX etc.) → Supabase Storage (Resource Supabase)
    → Upload via supabase_storage.py / storage_manager.py
    → Path stored in: CourseResource.firebase_file_path (misnomer — IS Supabase)
    → Access via 7-day signed URLs: CourseResource.get_signed_url()
    → Naming convention: courses/<course_uid>/resources/<uid>.<ext>

Proof PDFs (teacher/student credentials) → Supabase Storage (Main Supabase)
    → Path stored in: CustomUser.pdf_path
    → Access via: CustomUser.proof_pdf_url property
    → Organized into: documents/students/ or documents/teachers/

Google Drive → Backup storage (OAuth2 refresh token, personal Google account)
    → Real-time: triggered by post_save signals, background threads
    → Folders:
      NeoLearner_Backups/Signup_Proofs/YYYY/MM/
      NeoLearner_Backups/Teacher_Resources/{Course}/{Chapter}/{Category}/
      NeoLearner_Backups/Daily_Backups/  (from cron)
    → Tracked via CourseResource.backup_file_path + backup_status
    → Auth: GOOGLE_DRIVE_CLIENT_ID + CLIENT_SECRET + REFRESH_TOKEN (OAuth2)
```

---

## 🧩 AI TASK RULES

### ✅ Always Do
1. **Use `uid` (UUID) for all URL routing** — never integer PKs in public URLs
2. **Check `has_pending_edits` flag** before modifying approved content
3. **Use `get_signed_url()`** for resource file access — never expose raw storage paths
4. **Run `python manage.py makemigrations accounts`** after any model changes
5. **Work ONLY on `3-fullcorrect` branch** — never touch any other branch
6. **Add CSRF token** to all POST forms: `{% csrf_token %}`
7. **Check user type** (`request.user.user_type`) for role-based access control
8. **If unsure about a task involving other branches — ASK before proceeding**

### ❌ Never Do
1. Never hardcode Supabase/Cloudinary API keys — always use `os.getenv()`
2. Never expose `firebase_file_path`/`pdf_path` directly to templates
3. Never skip the `DeletionRequest` workflow for resource deletes
4. Never set `DEBUG=True` in production
5. Never add `X_FRAME_OPTIONS = 'ALLOWALL'` globally — only exempt specific views
6. Never commit `.env` or `db.sqlite3` to git
7. Never switch to, merge, sync, or reset any branch other than `3-fullcorrect`
8. Never create new branches unless explicitly asked

### Common Gotchas
- `CourseResource.firebase_file_path` = Supabase path (misleading field name from migration history)
- Admin login URL is hidden: `/customadmin/portal-secure-access/` (not `/customadmin/login/`)
- Chat admin identity is masked — `sender.user_type == 'ADMIN'` → display as "Support Team"
- `pdf_path` (new) vs `proof_pdf` (legacy deprecated) — always use `pdf_path`
- `SESSION_COOKIE_AGE = 10800` (3hr) applies only to students; admin/teacher use `session.set_expiry(0)`
- Google Drive backup uses OAuth2 (personal account), not service account
- `supabase` PyPI package version is **2.16.0** (not 1.2.0 as older docs state)
- Supabase SDK storage API for bucket CRUD uses direct HTTP — do NOT use `client.storage.get_bucket()` / `create_bucket()` (URL construction broken in v2.x)

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
- `custom_admin/templates/custom_admin/backup_center.html` — Backup management UI

---

## 🔍 CONTEXT PROCESSOR

`accounts/context_processors.py` — `pending_counts`
Available globally in all templates:
- `pending_user_count` — users awaiting approval
- `pending_course_count` — courses awaiting approval
- `pending_resource_count` — resources awaiting approval
- `pending_deletion_count` — deletion requests pending

---

## ⏰ CRON JOBS (cron-job.org)

| URL | Frequency | Purpose |
|:---|:---|:---|
| `.../cron-trigger/?token=<TOKEN>&type=supabase-db` | Every 4 hours | Live PostgreSQL restore (DATABASE_URL → BACKUP_DATABASE_URL) |
| `.../cron-trigger/?token=<TOKEN>&type=database` | Daily 20:30 UTC | Daily full backup (DB dump → 3rd Supabase bucket) |

Base URL: `https://neolearner.onrender.com/customadmin/backup-center/cron-trigger/`
Token: Stored in `BACKUP_CRON_TOKEN` env var.

---

## 🔐 KEY FILES REFERENCE

| File | Purpose |
|:---|:---|
| `accounts/utils/google_drive_service.py` | Google Drive API: upload, download, delete, retention, OAuth + service account |
| `accounts/utils/drive_backup_service.py` | Auto-router: OAuth → service account → MEGA fallback |
| `accounts/utils/backup_trigger.py` | Real-time backup: background threads, retry logic, SHA256 verify |
| `accounts/utils/generate_drive_token.py` | One-time OAuth refresh token generator (run locally) |
| `accounts/utils/supabase_storage.py` | Supabase storage: signed URLs, download, upload, backup client |
| `accounts/management/commands/backup_daily_full.py` | Daily full backup management command |
| `accounts/management/commands/backup_to_live_db.py` | Live DB restore management command |
| `accounts/management/commands/check_mega_backup.py` | Legacy check (no longer used) |
| `accounts/management/commands/backup_email_report.py` | Backup email report (no longer used) |

---

*This document is the single source of truth for any AI working on Neo Learner.*
*Updated: 2026-06-13. Maintain this file whenever models, URLs, or workflows change.*
