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
    let detail = response.statusText;
    let fieldErrors = {};
    try {
      const data = await response.json();
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
    } catch {}

    // Session expired or no auth: redirect to login instead of showing the
    // misleading "wrong password" toast. Skip when we're already on /login
    // (so failed logins keep showing their normal error).
    if (response.status === 401 && typeof window !== "undefined"
        && !window.location.pathname.includes("/login")) {
      try {
        sessionStorage.setItem("session_expired", "1");
      } catch {}
      window.location.href = "/admin/login";
      throw new ApiError(401, "Session expired");
    }

    if (!options.silent) toast.error(detail);
    throw new ApiError(response.status, detail, fieldErrors);
  }
  if (response.status === 204) return null;
  return response.json();
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
};

export { ApiError };
export default api;
