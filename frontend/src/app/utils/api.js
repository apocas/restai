import { toast } from 'react-toastify';

class ApiError extends Error {
  constructor(status, detail, fieldErrors = {}) {
    super(detail);
    this.status = status;
    this.detail = detail;
    // Map of field name -> first error message, parsed from FastAPI's
    // Pydantic-422 `detail` array. Forms can consume this to mark the
    // offending TextField with `error` + `helperText`.
    this.fieldErrors = fieldErrors;
  }
}

// Pull a field-path → message map out of FastAPI's 422 detail shape.
// FastAPI returns `[{loc:[...], msg:"...", type:"..."}, ...]` where loc
// is ["body", "field_name"] (or ["path", "..."] / ["query", "..."]).
// We flatten multi-level body locs to "a.b" so nested models still work.
function _extractFieldErrors(detail) {
  if (!Array.isArray(detail)) return {};
  const out = {};
  for (const err of detail) {
    if (!err || !Array.isArray(err.loc) || err.loc.length < 2) continue;
    const [scope, ...rest] = err.loc;
    if (scope !== "body" && scope !== "query" && scope !== "path") continue;
    const key = rest.join(".");
    if (!key) continue;
    let msg = err.msg || err.message || "";
    if (msg.startsWith("Value error, ")) msg = msg.slice("Value error, ".length);
    if (!(key in out)) out[key] = msg;
  }
  return out;
}

// Turn a failed response into an ApiError, running the shared side effects
// (401 redirect, error toast). Split out of `request` so the XHR-based
// `upload` path below reports errors identically instead of growing its own
// slightly-different copy.
function _buildApiError(status, statusText, rawBody, silent) {
  let detail = statusText;
  let fieldErrors = {};
  try {
    const data = JSON.parse(rawBody);
    let d = data.detail || detail;
    if (Array.isArray(d)) {
      // FastAPI validation error shape — extract per-field before
      // collapsing to a toast string so forms can still show inline.
      fieldErrors = _extractFieldErrors(d);
      d = d.map(e => e.msg || e.message || JSON.stringify(e)).join("; ");
    }
    // Legacy: stringified dict with 'msg' key (older endpoints).
    if (typeof d === "string" && d.includes("'msg':")) {
      const match = d.match(/'msg':\s*'([^']+)'/);
      if (match) d = match[1];
    }
    detail = d;
  } catch {
    // A 413 raised by a reverse proxy (nginx `client_max_body_size`) never
    // reaches the app, so there is no JSON envelope — just an HTML page.
    // `statusText` alone ("Request Entity Too Large") doesn't tell the admin
    // the limit is in front of RESTai, not in it.
    if (status === 413) {
      detail = "Upload rejected as too large before it reached RESTai — "
             + "raise the reverse proxy's body-size limit (nginx: client_max_body_size).";
    }
  }

  // Session expired or no auth: redirect to login instead of showing the
  // misleading "wrong password" toast. Skip when we're already on /login
  // (so failed logins keep showing their normal error).
  if (status === 401 && typeof window !== "undefined"
      && !window.location.pathname.includes("/login")) {
    try {
      sessionStorage.setItem("session_expired", "1");
    } catch {}
    window.location.href = "/admin/login";
    return new ApiError(401, "Session expired");
  }

  if (!silent) toast.error(detail);
  return new ApiError(status, detail, fieldErrors);
}

async function request(path, options = {}, token = null) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const headers = new Headers(options.headers || {});
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', 'Basic ' + token);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url + path, { ...options, headers });
  if (!response.ok) {
    let raw = "";
    try { raw = await response.text(); } catch {}
    throw _buildApiError(response.status, response.statusText, raw, options.silent);
  }
  if (response.status === 204) return null;
  return response.json();
}

// `fetch` cannot report upload progress — there is no readable stream on the
// request side in any shipping browser. XHR can, so file uploads go through
// this instead. Error handling is shared with `request` via _buildApiError so
// callers see the same ApiError (status / detail / fieldErrors).
function upload(path, formData, token, opts = {}) {
  const { onProgress, signal, silent, method = 'POST' } = opts;
  const url = (process.env.REACT_APP_RESTAI_API_URL || "") + path;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    if (token) xhr.setRequestHeader('Authorization', 'Basic ' + token);
    // Content-Type is deliberately unset: the browser has to add the
    // multipart boundary itself.

    if (onProgress && xhr.upload) {
      xhr.upload.onprogress = (e) => {
        // Not computable for a chunked/streamed body — report indeterminate
        // rather than a bogus 0%.
        onProgress(e.lengthComputable ? e.loaded / e.total : null, e.loaded, e.total);
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        if (xhr.status === 204 || !xhr.responseText) return resolve(null);
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          resolve(null);
        }
        return;
      }
      reject(_buildApiError(xhr.status, xhr.statusText, xhr.responseText, silent));
    };

    xhr.onerror = () => {
      // A body-size rejection can arrive as a connection reset rather than a
      // response, because the server stops reading mid-upload.
      reject(_buildApiError(0, "Network error during upload", "", silent));
    };
    xhr.ontimeout = () => reject(_buildApiError(0, "Upload timed out", "", silent));

    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return reject(new ApiError(0, "Upload cancelled"));
      }
      signal.addEventListener('abort', () => xhr.abort(), { once: true });
      xhr.onabort = () => reject(new ApiError(0, "Upload cancelled"));
    }

    xhr.send(formData);
  });
}

const api = {
  get: (path, token, opts = {}) => request(path, { method: 'GET', ...opts }, token),
  post: (path, body, token, opts = {}) => request(path, {
    method: 'POST',
    body: body instanceof FormData ? body : JSON.stringify(body), ...opts
  }, token),
  patch: (path, body, token, opts = {}) => request(path, {
    method: 'PATCH', body: JSON.stringify(body), ...opts
  }, token),
  put: (path, body, token, opts = {}) => request(path, {
    method: 'PUT', body: JSON.stringify(body), ...opts
  }, token),
  delete: (path, token, opts = {}) => request(path, { method: 'DELETE', ...opts }, token),
  raw: request,
  upload,
};

export { ApiError };
export default api;
