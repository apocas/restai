import api, { ApiError } from "./api";
import { toast } from "react-toastify";

jest.mock("react-toastify", () => ({
  toast: { error: jest.fn() },
}));

const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  statusText: `HTTP ${status}`,
  json: () => Promise.resolve(body),
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
