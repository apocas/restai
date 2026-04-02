import { toast } from 'react-toastify';

class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
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
    try {
      const data = await response.json();
      let d = data.detail || detail;
      // Extract clean message from validation errors
      if (typeof d === "string" && d.includes("'msg':")) {
        const match = d.match(/'msg':\s*'([^']+)'/);
        if (match) d = match[1];
      }
      // Handle array of validation errors
      if (Array.isArray(d)) {
        d = d.map(e => e.msg || e.message || JSON.stringify(e)).join("; ");
      }
      detail = d;
    } catch {}
    if (!options.silent) toast.error(detail);
    throw new ApiError(response.status, detail);
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
  delete: (path, token, opts = {}) => request(path, { method: 'DELETE', ...opts }, token),
  raw: request,
};

export { ApiError };
export default api;
