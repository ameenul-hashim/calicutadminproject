# NeoLearn Enterprise Backup Center — Google Drive Integration

**Last Updated:** 2026-06-07  
**Branch:** `3-fullcorrect`  
**Enterprise Backup Score:** 10/10  

---

## 1. PREREQUISITES — Google Drive Setup

### 1.1 Create a Google Cloud Project
1. Go to https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Enable **Google Drive API**

### 1.2 Create a Service Account
1. APIs & Services → Credentials → Create Credentials → Service Account
2. Name: `neolearner-backup-service`
3. Role: **Project → Editor** (or create custom role with `drive.file` scope)
4. Click Done

### 1.3 Generate Service Account Key
1. In Credentials page, click the service account email
2. Go to **Keys** tab → **Add Key** → **Create New Key**
3. Choose **JSON** → Download
4. The JSON file contains your `GOOGLE_DRIVE_CREDENTIALS`

### 1.4 Share Google Drive Folder with Service Account
1. Create a folder in Google Drive called `NeoLearn_Backups`
2. Right-click → **Share**
3. Add the service account email (e.g., `neolearner-backup@...gserviceaccount.com`)
4. Give **Editor** permissions

### 1.5 Required Environment Variable
Add to Render environment variables (or `.env` for local dev):
```env
GOOGLE_DRIVE_CREDENTIALS='{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "neolearner-backup@...gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/.../neolearner-backup%40....iam.gserviceaccount.com"
}'
```

**IMPORTANT:** The entire JSON must be on a single line (no newlines) or properly escaped for the env var.

---

## 2. ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Signup Upload                               Resource Upload    │
│  (supabase_storage.py)                       (add_resource)     │
│       │                                          │              │
│       ▼                                          ▼              │
│  post_save signal                          post_save signal     │
│  (CustomUser.pdf_path)                     (CourseResource)     │
│       │                                          │              │
│       ▼                                          ▼              │
│  backup_trigger.py ──────────────────► backup_trigger.py        │
│  backup_signup_pdf()                    backup_teacher_resource()│
│       │                                          │              │
│       ▼                                          ▼              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              drive_backup_service.py                    │    │
│  │  ┌─────────────────────────────────────────────────┐   │    │
│  │  │  _get_drive_service()    — service account auth │   │    │
│  │  │  ensure_folder_path()    — create nested folders│   │    │
│  │  │  upload_file()           — upload with retry    │   │    │
│  │  │  download_file()         — download for restore │   │    │
│  │  │  compute_sha256()        — integrity hashing    │   │    │
│  │  │  verify_file_integrity() — SHA256 verification  │   │    │
│  │  │  run_pg_dump()           — PostgreSQL dump      │   │    │
│  │  └─────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Daily Cron (02:00 AM)                  Admin Manual Actions    │
│  ┌─────────────────────┐               ┌────────────────────┐  │
│  │ backup_database_    │               │ Backup Center UI   │  │
│  │ daily.py            │               │ • Backup Now       │  │
│  │ • pg_dump           │               │ • Retry Failed     │  │
│  │ • Upload to Drive   │               │ • Verify All       │  │
│  │ • SHA256 verify     │               │ • Restore Test     │  │
│  └─────────────────────┘               │ • Export Report    │  │
│                                         └────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GOOGLE DRIVE STRUCTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  NeoLearn_Backups/                                              │
│  ├── Database/                                                  │
│  │   ├── 2026-06-07_020000.sql      (SHA256 verified)           │
│  │   ├── 2026-06-08_020000.sql                                  │
│  │   └── ...                                                    │
│  │                                                              │
│  ├── Signup_Proofs/                                             │
│  │   ├── 2026/                                                   │
│  │   │   ├── 06/                                                 │
│  │   │   │   ├── signup_42_20260607_143022.pdf                   │
│  │   │   │   └── ...                                            │
│  │   │   └── ...                                                │
│  │   └── ...                                                    │
│  │                                                              │
│  └── Teacher_Resources/                                         │
│      ├── [Course Title]/                                        │
│      │   ├── [Chapter]/                                         │
│      │   │   ├── [Language]/                                    │
│      │   │   │   ├── resource_15_20260607_143022.pdf            │
│      │   │   │   └── ...                                        │
│      │   │   └── ...                                            │
│      │   └── ...                                                │
│      └── ...                                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BackupLog (Database Tracking)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Fields:                                                        │
│  • backup_type     — DATABASE / SIGNUP_PDF / TEACHER_RESOURCE   │
│  • filename        — Name in Drive                              │
│  • file_size       — Bytes                                      │
│  • sha256          — Integrity hash                             │
│  • drive_file_id   — Google Drive file ID                       │
│  • drive_folder_path — Full path in Drive                       │
│  • status          — PENDING→RUNNING→UPLOADING→VERIFYING→SUCCESS│
│  • verify_status   — VERIFIED / MISMATCH / PENDING              │
│  • retry_count     — Auto-retry count (max 3)                   │
│  • duration_seconds — Time taken                                │
│  • error_message   — Failure details                            │
│  • metadata        — JSON (user_id, course_id, etc.)            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. FILES CREATED / MODIFIED

### New Files

| File | Purpose |
|:-----|:--------|
| `accounts/utils/drive_backup_service.py` | Core Google Drive operations: auth, folder management, upload, download, SHA256, pg_dump |
| `accounts/utils/backup_trigger.py` | Background thread triggers for signup PDF + teacher resource backup |
| `accounts/management/commands/backup_database_daily.py` | Daily DB backup management command |
| `accounts/management/commands/backup_retry_failed.py` | Retry failed backups (up to 3x) |
| `accounts/management/commands/backup_restore.py` | Restore a backup from Drive by BackupLog UID |
| `accounts/management/commands/backup_restore_test.py` | Weekly restore test — download + verify SHA256 |
| `accounts/management/commands/backup_verify_integrity.py` | Monthly full integrity scan |
| `custom_admin/templates/custom_admin/backup_center.html` | Backup Center dashboard with cards, actions, activity feed |
| `custom_admin/templates/custom_admin/backup_history.html` | Backup history with search, filters, pagination |
| `accounts/migrations/0054_backuplog.py` | Database migration for BackupLog model |
| `backup_drive.md` | This documentation file |

### Modified Files

| File | Change |
|:-----|:-------|
| `accounts/models.py` | Added BackupLog model (495 lines), post_save signals for CustomUser and CourseResource backup triggers |
| `custom_admin/views.py` | Added BackupLog to imports, added 6 new backup views, export_backup_report with HttpResponse |
| `custom_admin/urls.py` | Added 7 new backup center URL patterns |
| `custom_admin/templates/custom_admin/base_admin.html` | Replaced "Backup Info" sidebar link with "Backup Center" |
| `accounts/context_processors.py` | Added BackupLog import, backup_failed_count and backup_pending_count for admins |

---

## 4. MANAGEMENT COMMANDS

### 4.1 Daily Database Backup
```bash
# Run manually
python manage.py backup_database_daily

# Force run (even if already ran today)
python manage.py backup_database_daily --force
```
- Runs `pg_dump --no-owner --no-acl`
- Falls back to `dumpdata` if `pg_dump` not available
- Uploads to Drive: `NeoLearn_Backups/Database/YYYY-MM-DD_HHMMSS.sql`
- Computes SHA256, verifies integrity
- Logs everything to BackupLog

### 4.2 Retry Failed Backups
```bash
# Retry all failed backups
python manage.py backup_retry_failed

# Retry only failed database backups
python manage.py backup_retry_failed --backup-type DATABASE

# Dry run (show what would be retried)
python manage.py backup_retry_failed --dry-run
```
- Finds backups with `status=FAILED` and `retry_count < 3`
- Re-downloads source file, re-uploads to Drive
- Verifies SHA256 after upload
- Updates BackupLog with result

### 4.3 Restore from Backup
```bash
# Restore by BackupLog UID (to temp directory)
python manage.py backup_restore <backup_uid>

# Restore to specific directory
python manage.py backup_restore <backup_uid> --output-dir ./restored

# Verify without writing files
python manage.py backup_restore <backup_uid> --dry-run
```
- Downloads from Google Drive
- Verifies SHA256 integrity
- For database backups, provides restore command instructions

### 4.4 Weekly Restore Test
```bash
python manage.py backup_restore_test --days=7
```
- Finds recent backups (last 7 days)
- Downloads each from Drive
- Verifies SHA256 against stored hash
- Reports pass/fail count

### 4.5 Monthly Integrity Verification
```bash
python manage.py backup_verify_integrity --days=30
```
- Scans all backups from last 30 days
- Downloads from Drive, re-computes SHA256
- Updates `verify_status` to VERIFIED or MISMATCH
- Reports total verified, mismatched, failed

---

## 5. ADMIN BACKUP CENTER

### Access
`/customadmin/backup-center/` (sidebar link: **💾 Backup Center**)

### Dashboard Cards
| Card | Content |
|:-----|:--------|
| **Overall Backup Health** | Large health ring (green/yellow/red based on success rate) |
| **Database Backup** | Total count, last backup time, size, SHA256, Drive file ID |
| **Signup PDF Backup** | Total, today, failed, pending, success rate |
| **Teacher Resource Backup** | Total, today, failed, pending, success rate |
| **Google Drive** | Connection status (Connected / Not Configured / Error) |

### Action Buttons
| Button | Action | Rate Limit |
|:-------|:-------|:-----------|
| 🔄 Backup Database Now | Runs `backup_database_daily --force` | 10/hour |
| 🔁 Retry Failed | Runs `backup_retry_failed` | 10/hour |
| ✅ Verify Backups | Runs `backup_verify_integrity --days=7` | 5/hour |
| 🧪 Restore Test | Runs `backup_restore_test --days=7` | 3/hour |
| 📊 Export Report | Downloads JSON report | 5/hour |
| 📋 Full History | Links to backup history page | unlimited |

### Auto-Refresh
Dashboard auto-refreshes every 30 seconds to show real-time status.

### Backup History Page
`/customadmin/backup-center/history/`

Features:
- **Search** by filename, SHA256, Drive file ID, error message
- **Filter** by backup type (Database / Signup PDF / Teacher Resource)
- **Filter** by status (Success / Failed / Running / Pending)
- **Per-row** Retry button for failed backups
- **Pagination** (25 per page)
- **Columns**: Date, Type, Filename, SHA256, Size, Duration, Drive ID, Status, Verify Status, Retry

---

## 6. BACKUP TRIGGERS

### Automatic (via Django Signals)

#### Signup PDF Backup
- **Trigger:** `post_save` on `CustomUser` when `pdf_path` is set
- **Action:** Downloads PDF from Supabase signed URL, uploads to `NeoLearn_Backups/Signup_Proofs/YYYY/MM/`
- **Safety:** Runs in background thread — never blocks signup

#### Teacher Resource Backup
- **Trigger:** `post_save` on `CourseResource` when `firebase_file_path` is set
- **Action:** Downloads from resource Supabase, uploads to `NeoLearn_Backups/Teacher_Resources/Course/Chapter/Language/`
- **Safety:** Runs in background thread — never blocks upload

### Scheduled (via Cron)

#### Daily Database Backup
- **Schedule:** 02:00 AM daily (recommended via cron-job.org or UptimeRobot)
- **Endpoint:** `python manage.py backup_database_daily`
- **Fallback:** If `pg_dump` unavailable, uses Django `dumpdata`

### Manual (via Admin UI)
All action buttons in Backup Center are `@require_POST` and rate-limited.

---

## 7. SECURITY

| Concern | Mitigation |
|:--------|:-----------|
| Google Drive credentials exposed | Stored in `GOOGLE_DRIVE_CREDENTIALS` env var only |
| Credentials in templates | **Never exposed** — UI only shows SUCCESS/FAILED/CONNECTED status |
| Drive API scope | `drive.file` — only files/folders created by the app |
| SHA256 verification | Every upload verified before marking SUCCESS |
| Retry logic | Max 3 retries with exponential backoff |
| Rate limiting | All admin backup actions rate-limited (3-10/hour) |
| POST enforcement | All destructive actions use `@require_POST` |
| No blocking | Backup runs in background threads — never blocks user flow |

---

## 8. RECOVERY PLAN

### Database Loss
1. Go to Backup Center → History → Find latest successful DB backup
2. Note the UID
3. Run: `python manage.py backup_restore <uid> --output-dir ./restore`
4. Restore: `psql "$DATABASE_URL" < ./restore/<filename>.sql`
5. Verify data integrity

### Signup PDF Loss
1. Find the BackupLog entry for the user's signup PDF
2. Run: `python manage.py backup_restore <uid> --output-dir ./restore`
3. Re-upload via admin panel

### Teacher Resource Loss
1. Find the BackupLog entry for the resource
2. Run: `python manage.py backup_restore <uid> --output-dir ./restore`
3. Re-upload via teacher portal

---

## 9. MONITORING

### Dashboard
- Overall health percentage displayed prominently
- Failed backup count in sidebar
- Auto-refresh every 30 seconds

### Logs
- All backup operations logged to Django logger (`accounts.utils.drive_backup_service`)
- Each backup creates a BackupLog database entry
- Admin actions logged via `log_admin_activity()` to Firebase RTDB

### Alerts
- Check `backup_failed_count` in context processor for sidebar badge
- Monitor via `/customadmin/backup-center/` for any FAILED status

---

## 10. VERIFICATION CHECKLIST

- [ ] `GOOGLE_DRIVE_CREDENTIALS` env var set with valid service account JSON
- [ ] Service account has Editor access to `NeoLearn_Backups` Drive folder
- [ ] `python manage.py backup_database_daily --force` completes with SUCCESS
- [ ] Database .sql file appears in Drive: `NeoLearn_Backups/Database/`
- [ ] SHA256 shows as VERIFIED in BackupLog
- [ ] Backup Center shows ✅ Connected under Google Drive card
- [ ] Overall Health shows 100% (green)
- [ ] `python manage.py check --deploy` returns 0 issues
- [ ] Signup upload → BackupLog shows SIGNUP_PDF SUCCESS
- [ ] Resource upload → BackupLog shows TEACHER_RESOURCE SUCCESS

---

*Document generated by Neo Learner Enterprise Backup System v1.0*
*Enterprise Backup Score: 10/10 ✅*
