// Pairing credentials: parse the QR/paste payload, validate the key, and
// persist locally. NOTE: localStorage is the only practical option for a web
// app — it is NOT encrypted at rest like the Android EncryptedSharedPreferences,
// so the API key lives in plaintext in the browser profile. The key is
// read-only + project-scoped, and regenerating it in the admin revokes it.
const KEY = "restai_mobile_creds";

export function parsePayload(raw) {
  try {
    const j = JSON.parse(String(raw).trim());
    const host = String(j.host || "").replace(/\/+$/, "");
    const projectId = parseInt(j.project_id, 10);
    const apiKey = String(j.api_key || "");
    if (!host || !Number.isFinite(projectId) || projectId <= 0 || !apiKey) return null;
    return {
      host,
      projectId,
      projectName: j.project_name || `project ${projectId}`,
      apiKey,
    };
  } catch {
    return null;
  }
}

// Validate the scanned key against the host before committing (mirrors the
// Android app's whoami probe at pairing time).
export async function whoami(host, apiKey) {
  try {
    const r = await fetch(`${host}/auth/whoami`, {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    return r.ok;
  } catch {
    return false;
  }
}

export function loadCreds() {
  try {
    const c = JSON.parse(localStorage.getItem(KEY) || "null");
    if (c && c.host && c.projectId && c.apiKey) return c;
  } catch {
    /* ignore */
  }
  return null;
}

export function saveCreds(c) {
  localStorage.setItem(KEY, JSON.stringify(c));
}

export function clearCreds() {
  localStorage.removeItem(KEY);
}
