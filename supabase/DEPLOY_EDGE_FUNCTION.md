# Deploy Supabase Edge Function: drive-backup

## Prerequisites
- Supabase CLI: `npm install -g supabase` or `brew install supabase/tap/supabase`
- Logged in: `supabase login`
- You have **two** Supabase projects (main + resource). Deploy to **main Supabase** only.

## Step 1: Link to Main Supabase project
```bash
supabase link --project-ref ypcebdfiiohtgrptnmwv
```

## Step 2: Set secrets on Main Supabase
```bash
supabase secrets set GOOGLE_DRIVE_CLIENT_ID="<your-client-id>"
supabase secrets set GOOGLE_DRIVE_CLIENT_SECRET="<your-client-secret>"
supabase secrets set GOOGLE_DRIVE_REFRESH_TOKEN="<your-refresh-token>"
```

Use the exact values from your `.env` file.

Note: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are auto-injected by Supabase runtime — no need to set them manually.

## Step 3: Deploy the function
```bash
supabase functions deploy drive-backup --no-verify-jwt
```

After deploy, note the function URL:
```
https://ypcebdfiiohtgrptnmwv.supabase.co/functions/v1/drive-backup
```

## Step 4: Create Storage webhook on Main Supabase
In the Supabase Dashboard for **Main Supabase** (`ypcebdfiiohtgrptnmwv`):
1. Go to **Database → Webhooks**
2. Click **Create a new hook**
3. Configure:
   - Name: `Drive Backup - Signup Proofs`
   - Table: `objects`
   - Events: `INSERT`
   - HTTP Request URL: `https://ypcebdfiiohtgrptnmwv.supabase.co/functions/v1/drive-backup`
   - Headers: `Content-Type: application/json`
4. Save

This handles signup proofs uploaded to the `calicutadminpanelpdf` bucket.

## Step 5: Create Storage webhook on Resource Supabase
In the Supabase Dashboard for **Resource Supabase** (`wahfxicsaygqzgefmkta`):
1. Go to **Database → Webhooks**
2. Click **Create a new hook**
3. Configure:
   - Name: `Drive Backup - Teacher Resources`
   - Table: `objects`
   - Events: `INSERT`
   - HTTP Request URL: `https://ypcebdfiiohtgrptnmwv.supabase.co/functions/v1/drive-backup`
   - Headers:
     - `Content-Type: application/json`
     - `X-Resource-URL: <your-RESOURCE_SUPABASE_URL>` (value from `.env`)
     - `X-Resource-Key: <your-RESOURCE_SUPABASE_SERVICE_ROLE_KEY>` (value from `.env`)
4. Save

This handles teacher resources uploaded to the `resources` bucket.

## Step 6: Deploy Django changes to Render
Just push `3-fullcorrect` to GitHub — Render auto-deploys:
```bash
git add -A
git commit -m "feat: zero-RAM browser-direct upload + Edge Function drive backup"
git push origin 3-fullcorrect
```

## Step 7: Verify
1. Upload a PDF (signup or resource) through the app
2. Check Edge Function logs: Supabase Dashboard → Edge Functions → drive-backup → Logs
3. Check Google Drive → `NeoLearner_Backups/` folder for the uploaded file

## Env var cleanup (optional, safe to leave)
After Edge Function is working, these can be removed from Render:
- ~~`GOOGLE_DRIVE_CREDENTIALS`~~ (old service account — not used by OAuth flow)
- ~~`GOOGLE_DRIVE_ROOT_FOLDER_ID`~~ (not needed — folders auto-created)

Keep these on Render (still used by Django for signed URLs, etc.):
- `GOOGLE_DRIVE_CLIENT_ID` — still needed by `google_drive_service.py` (backup_center UI)
- `GOOGLE_DRIVE_CLIENT_SECRET` — same
- `GOOGLE_DRIVE_REFRESH_TOKEN` — same
