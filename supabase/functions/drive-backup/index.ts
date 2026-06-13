// Supabase Edge Function: drive-backup
// Triggered on new Supabase Storage object insert.
// Downloads the file and uploads to Google Drive (OAuth2).
// Zero Render RAM usage — runs entirely on Supabase's Deno runtime.
//
// Supports both Main Supabase (signup proofs) and Resource Supabase (teacher files).
// When deployed on Main Supabase, the Resource Supabase webhook should pass:
//   X-Resource-URL: https://<resource-project>.supabase.co
//   X-Resource-Key: service-role-key-of-resource

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";

const GOOGLE_DRIVE_CLIENT_ID = Deno.env.get("GOOGLE_DRIVE_CLIENT_ID")!;
const GOOGLE_DRIVE_CLIENT_SECRET = Deno.env.get("GOOGLE_DRIVE_CLIENT_SECRET")!;
const GOOGLE_DRIVE_REFRESH_TOKEN = Deno.env.get("GOOGLE_DRIVE_REFRESH_TOKEN")!;

const ROOT_FOLDER = "NeoLearner_Backups";

interface StorageEvent {
  type: "INSERT";
  table: string;
  record: {
    bucket_id: string;
    name: string;
  };
}

function getAccessToken(): Promise<string> {
  const resp = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: GOOGLE_DRIVE_CLIENT_ID,
      client_secret: GOOGLE_DRIVE_CLIENT_SECRET,
      refresh_token: GOOGLE_DRIVE_REFRESH_TOKEN,
      grant_type: "refresh_token",
    }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(`OAuth refresh failed: ${data.error_description || data.error}`);
  return data.access_token;
}

async function ensureFolder(token: string, path: string[]): Promise<string> {
  let parentId: string | null = null;
  for (const folderName of path) {
    let query = `name='${folderName.replace(/'/g, "\\'")}' and mimeType='application/vnd.google-apps.folder' and trashed=false`;
    if (parentId) query += ` and '${parentId}' in parents`;

    const resp = await fetch(
      `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(query)}&fields=files(id,name)`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    const data = await resp.json();
    if (data.files && data.files.length > 0) {
      parentId = data.files[0].id;
    } else {
      const createResp = await fetch("https://www.googleapis.com/drive/v3/files", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: folderName,
          mimeType: "application/vnd.google-apps.folder",
          parents: parentId ? [parentId] : [],
        }),
      });
      const created = await createResp.json();
      parentId = created.id;
    }
  }
  return parentId!;
}

async function uploadToDrive(
  token: string,
  fileBytes: Uint8Array,
  fileName: string,
  mimeType: string,
  folderId: string
): Promise<string> {
  const boundary = "drive-boundary-" + crypto.randomUUID();
  const encoder = new TextEncoder();
  const headerStr =
    `--${boundary}\r\n` +
    `Content-Type: application/json; charset=UTF-8\r\n\r\n` +
    JSON.stringify({ name: fileName, parents: [folderId] }) +
    `\r\n--${boundary}\r\n` +
    `Content-Type: ${mimeType}\r\n\r\n`;
  const footerStr = `\r\n--${boundary}--`;

  const body = new Uint8Array(encoder.encode(headerStr).length + fileBytes.length + encoder.encode(footerStr).length);
  body.set(encoder.encode(headerStr), 0);
  body.set(fileBytes, encoder.encode(headerStr).length);
  body.set(encoder.encode(footerStr), encoder.encode(headerStr).length + fileBytes.length);

  const resp = await fetch(
    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": `multipart/related; boundary=${boundary}`,
      },
      body,
    }
  );
  const data = await resp.json();
  if (!resp.ok) throw new Error(`Drive upload failed: ${data.error?.message || resp.status}`);
  return data.id;
}

function getDestinationPath(bucketId: string, name: string): { folder: string[]; fileName: string } {
  const parts = name.split("/");
  const fileName = parts.pop() || name;

  if (bucketId === "calicutadminpanelpdf") {
    // Signup proofs from Main Supabase
    const now = new Date();
    const year = now.getFullYear().toString();
    const month = (now.getMonth() + 1).toString().padStart(2, "0");
    return { folder: [ROOT_FOLDER, "Signup_Proofs", year, month], fileName };
  }

  if (bucketId === "resources" || bucketId === "resource_bucket" || name.includes("/resources/")) {
    // Teacher resources: <course_slug>/<category>/<name>.pdf
    const [courseSlug, category] = parts;
    return {
      folder: [ROOT_FOLDER, "Teacher_Resources", courseSlug || "Unknown", category || "General"],
      fileName: fileName,
    };
  }

  return { folder: [ROOT_FOLDER, "Daily_Backups"], fileName };
}

async function downloadFromSupabase(
  supabaseUrl: string,
  supabaseKey: string,
  bucketId: string,
  filePath: string
): Promise<{ bytes: Uint8Array; mimeType: string }> {
  const url = `${supabaseUrl}/storage/v1/object/${bucketId}/${filePath}`;
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${supabaseKey}` },
  });
  if (!resp.ok) throw new Error(`Download failed: ${resp.status} ${await resp.text()}`);
  const bytes = new Uint8Array(await resp.arrayBuffer());
  const mimeType = resp.headers.get("content-type") || "application/octet-stream";
  return { bytes, mimeType };
}

serve(async (req) => {
  try {
    // Determine which Supabase instance triggered this
    // If called from Resource Supabase webhook, it passes headers with its own creds
    let supabaseUrl = req.headers.get("X-Resource-URL") || Deno.env.get("SUPABASE_URL")!;
    let supabaseKey = req.headers.get("X-Resource-Key") || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

    if (!supabaseUrl || !supabaseKey) {
      return new Response(JSON.stringify({ error: "No Supabase credentials available" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }

    const event: StorageEvent = await req.json();

    if (event.type !== "INSERT" || !event.record.bucket_id) {
      return new Response("Ignored: not a storage INSERT", { status: 200 });
    }

    const { bucket_id: bucketId, name: filePath } = event.record;

    if (filePath.startsWith("daily_backups/")) {
      return new Response("Skipped: daily backup file", { status: 200 });
    }

    const { bytes, mimeType } = await downloadFromSupabase(supabaseUrl, supabaseKey, bucketId, filePath);
    const token = await getAccessToken();
    const { folder, fileName } = getDestinationPath(bucketId, filePath);
    const folderId = await ensureFolder(token, folder);
    await uploadToDrive(token, bytes, fileName, mimeType, folderId);

    console.log(`Backed up ${bucketId}/${filePath} \u2192 Drive: ${folder.join("/")}/${fileName}`);

    return new Response(JSON.stringify({ success: true, path: `${folder.join("/")}/${fileName}` }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Edge function error:", error);
    return new Response(JSON.stringify({ success: false, error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
});
