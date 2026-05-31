# BACKUP & DISASTER RECOVERY AUDIT
**Strategy:** Multi-Cloud Redundancy
**Retention:** 30 Days Historical Snapshots

## 1. BACKUP PIPELINE OVERVIEW
The system employs an automated archival pipeline (`auto_backup.py`) that synchronizes both structured and unstructured data across geographically distributed clouds.

| Data Type | Source | Destination | Frequency |
| :--- | :--- | :--- | :--- |
| **Database** | Render PG | Google Drive | Daily (Automated) |
| **Verification PDFs**| Supabase | Google Drive | Daily (Archival) |
| **Configuration** | Environment | Secure Secret Store| Manual/Deployment |

## 2. INTEGRITY & VERIFICATION
*   **Checksums**: MD5 hashes are generated for every backup file and verified post-upload to ensure zero data corruption during transit.
*   **Logging**: All operations are logged to `backup.log` with RotatingFileHandlers (5MB limit).
*   **Alerting**: Automated alerts sent via Email and Telegram upon pipeline failure or cost-guardrail breach (500MB threshold).

## 3. RECOVERY WORKFLOWS
### 🔄 Database Restore (RTO: 15 mins)
1.  Download latest `.sql` dump from Google Drive.
2.  Import via `psql -d <db_url> -f <backup_file>`.
3.  Verify record counts against `backup.log`.

### 🔄 PDF Restore (RTO: 30 mins)
1.  Pull archived PDFs from Google Drive storage.
2.  Re-upload to Supabase `calicutadminpanelpdf` bucket.
3.  Sync `pdf_path` in `CustomUser` model if necessary.

## 4. DISASTER SCENARIOS
*   **Render Failure**: Deploy code to fallback provider (e.g., Fly.io/AWS) using environment secrets and restore DB from Google Drive.
*   **Supabase Failure**: Point `PortalSecurityMiddleware` to archived PDFs in Google Drive or a secondary S3 bucket.
*   **Data Corruption**: Roll back to the previous day's verified SQL snapshot from the Google Drive 30-day historical archive.

---
**Status:** ✅ **BACKUP ECOSYSTEM VERIFIED**
The recovery strategy is robust, automated, and tested for multi-point failure scenarios.
