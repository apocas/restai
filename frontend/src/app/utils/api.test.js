import api, { ApiError } from "./api";
import { toast } from "react-toastify";

jest.mock("react-toastify", () => ({
  toast: { error: jest.fn() },
}));

// Mirrors the parts of a real Response the client touches. `text()` matters
// on the error path: the client reads the body as text and parses it itself,
// so a non-JSON error page (a reverse proxy's 413) doesn't throw.
const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  statusText: `HTTP ${status}`,
  json: () => Promise.resolve(body),
  text: () => Promise.resolve(JSON.stringify(body)),
});

const textResponse = (status, body, statusText) => ({
  ok: status >= 200 && status < 300,
  status,
  statusText: statusText || `HTTP ${status}`,
  json: () => Promise.reject(new Error("not json")),
  text: () => Promise.resolve(body),
});

beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = jest.fn();
  sessionStorage.clear();
});

afterAll(() => {
  delete global.fetch;
});

describe("api client", () => {
  it("GET returns parsed JSON and sends Basic auth from the token", async () => {
    global.fetch.mockResolvedValue(jsonResponse(200, { hello: "world" }));
    const out = await api.get("/users", "dG9rZW4=");
    expect(out).toEqual({ hello: "world" });
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe("/users");
    expect(opts.headers.get("Authorization")).toBe("Basic dG9rZW4=");
  });

  it("POST serializes the body and sets JSON content type", async () => {
    global.fetch.mockResolvedValue(jsonResponse(200, {}));
    await api.post("/projects", { name: "p1" }, null);
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ name: "p1" }));
    expect(opts.headers.get("Content-Type")).toBe("application/json");
  });

  it("POST passes FormData through untouched (no forced content type)", async () => {
    global.fetch.mockResolvedValue(jsonResponse(200, {}));
    const fd = new FormData();
    fd.append("file", new Blob(["x"]), "x.txt");
    await api.post("/upload", fd, null);
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.body).toBe(fd);
    expect(opts.headers.get("Content-Type")).toBeNull();
  });

  it("returns null on 204 No Content", async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 204, json: () => Promise.reject() });
    await expect(api.delete("/projects/1", null)).resolves.toBeNull();
  });

  it("throws ApiError with detail and toasts on plain failures", async () => {
    global.fetch.mockResolvedValue(jsonResponse(403, { detail: "Forbidden thing" }));
    await expect(api.get("/x", null)).rejects.toMatchObject({
      status: 403,
      detail: "Forbidden thing",
    });
    expect(toast.error).toHaveBeenCalledWith("Forbidden thing");
  });

  it("suppresses the toast with the silent option", async () => {
    global.fetch.mockResolvedValue(jsonResponse(403, { detail: "quiet" }));
    await expect(api.get("/x", null, { silent: true })).rejects.toBeInstanceOf(ApiError);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("parses FastAPI 422 arrays into fieldErrors and a joined message", async () => {
    const detail = [
      { loc: ["body", "options", "rate_limit"], msg: "Value error, too big" },
      { loc: ["body", "name"], msg: "field required" },
      { loc: ["header", "x"], msg: "ignored scope" },
      { loc: ["body"], msg: "too-short loc ignored" },
    ];
    global.fetch.mockResolvedValue(jsonResponse(422, { detail }));
    let err;
    try {
      await api.post("/projects", {}, null);
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    // "Value error, " prefix stripped; nested body loc flattened with dots
    expect(err.fieldErrors).toEqual({
      "options.rate_limit": "too big",
      name: "field required",
    });
    expect(err.detail).toContain("field required");
  });

  it("extracts the msg from legacy stringified-dict details", async () => {
    global.fetch.mockResolvedValue(
      jsonResponse(400, { detail: "{'type': 'x', 'msg': 'Legacy message here'}" })
    );
    await expect(api.get("/x", null)).rejects.toMatchObject({ detail: "Legacy message here" });
  });

  it("redirects to login and flags the session on 401 outside /login", async () => {
    const original = window.location;
    delete window.location;
    window.location = { pathname: "/admin/projects", href: "" };
    try {
      global.fetch.mockResolvedValue(jsonResponse(401, { detail: "nope" }));
      await expect(api.get("/x", null)).rejects.toMatchObject({ detail: "Session expired" });
      expect(sessionStorage.getItem("session_expired")).toBe("1");
      expect(window.location.href).toBe("/admin/login");
      expect(toast.error).not.toHaveBeenCalled();
    } finally {
      window.location = original;
    }
  });

  it("does NOT redirect on 401 when already on the login page", async () => {
    const original = window.location;
    delete window.location;
    window.location = { pathname: "/admin/login", href: "" };
    try {
      global.fetch.mockResolvedValue(jsonResponse(401, { detail: "bad creds" }));
      await expect(api.get("/x", null)).rejects.toMatchObject({ status: 401, detail: "bad creds" });
      expect(window.location.href).toBe("");
      expect(toast.error).toHaveBeenCalledWith("bad creds");
    } finally {
      window.location = original;
    }
  });
});

describe("proxy-level errors without a JSON envelope", () => {
  it("explains a 413 raised in front of the app", async () => {
    global.fetch.mockResolvedValue(
      textResponse(413, "<html><head><title>413</title></head></html>", "Request Entity Too Large")
    );
    await expect(api.post("/projects/1/ingest-bulk", {}, null)).rejects.toMatchObject({
      status: 413,
    });
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining("client_max_body_size")
    );
  });

  it("falls back to statusText for other non-JSON bodies", async () => {
    global.fetch.mockResolvedValue(textResponse(502, "<html>bad gateway</html>", "Bad Gateway"));
    await expect(api.get("/info", null)).rejects.toMatchObject({
      status: 502,
      detail: "Bad Gateway",
    });
  });
});

describe("api.upload", () => {
  // `fetch` cannot report upload progress, so uploads go through XHR. Stub
  // the class rather than the network so the progress + error plumbing is
  // exercised deterministically.
  let xhr;

  class MockXHR {
    constructor() {
      this.upload = {};
      this.headers = {};
      this.status = 0;
      this.statusText = "";
      this.responseText = "";
      xhr = this;
    }
    open(method, url) {
      this.method = method;
      this.url = url;
    }
    setRequestHeader(k, v) {
      this.headers[k] = v;
    }
    send(body) {
      this.sent = body;
    }
    abort() {
      this.aborted = true;
      if (this.onabort) this.onabort();
    }
  }

  beforeEach(() => {
    global.XMLHttpRequest = MockXHR;
  });

  afterAll(() => {
    delete global.XMLHttpRequest;
  });

  it("POSTs the FormData with Basic auth and no forced content type", async () => {
    const form = new FormData();
    const p = api.upload("/projects/1/ingest-bulk", form, "dG9rZW4=");
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("/projects/1/ingest-bulk");
    expect(xhr.headers.Authorization).toBe("Basic dG9rZW4=");
    // The browser must set Content-Type so it can add the multipart boundary.
    expect(xhr.headers["Content-Type"]).toBeUndefined();
    expect(xhr.sent).toBe(form);

    xhr.status = 202;
    xhr.responseText = JSON.stringify({ queued: [1, 2], count: 2 });
    xhr.onload();
    await expect(p).resolves.toEqual({ queued: [1, 2], count: 2 });
  });

  it("reports fractional progress, and null when the length is unknown", async () => {
    const seen = [];
    const p = api.upload("/x", new FormData(), null, {
      onProgress: (pct) => seen.push(pct),
    });
    xhr.upload.onprogress({ lengthComputable: true, loaded: 25, total: 100 });
    xhr.upload.onprogress({ lengthComputable: true, loaded: 100, total: 100 });
    xhr.upload.onprogress({ lengthComputable: false, loaded: 5, total: 0 });
    expect(seen).toEqual([0.25, 1, null]);

    xhr.status = 200;
    xhr.responseText = "{}";
    xhr.onload();
    await p;
  });

  it("rejects with an ApiError carrying the server's detail", async () => {
    const p = api.upload("/x", new FormData(), null);
    xhr.status = 413;
    xhr.statusText = "Payload Too Large";
    xhr.responseText = JSON.stringify({ detail: "File too large. Max size: 100 MB" });
    xhr.onload();
    await expect(p).rejects.toMatchObject({
      status: 413,
      detail: "File too large. Max size: 100 MB",
    });
    expect(toast.error).toHaveBeenCalledWith("File too large. Max size: 100 MB");
  });

  it("surfaces 422 field errors the same way the fetch path does", async () => {
    const p = api.upload("/x", new FormData(), null);
    xhr.status = 422;
    xhr.responseText = JSON.stringify({
      detail: [{ loc: ["query", "chunks"], msg: "Input should be less than or equal to 8192" }],
    });
    xhr.onload();
    await expect(p).rejects.toMatchObject({
      status: 422,
      fieldErrors: { chunks: "Input should be less than or equal to 8192" },
    });
  });

  it("aborts when the caller's signal fires", async () => {
    const controller = new AbortController();
    const p = api.upload("/x", new FormData(), null, { signal: controller.signal });
    controller.abort();
    expect(xhr.aborted).toBe(true);
    await expect(p).rejects.toBeInstanceOf(ApiError);
  });

  it("does not toast when silent", async () => {
    const p = api.upload("/x", new FormData(), null, { silent: true });
    xhr.status = 500;
    xhr.responseText = JSON.stringify({ detail: "boom" });
    xhr.onload();
    await expect(p).rejects.toMatchObject({ status: 500 });
    expect(toast.error).not.toHaveBeenCalled();
  });
});
