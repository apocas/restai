import { formatChatError } from "./chatErrors";

// i18n `t` stub: returns the key, appending interpolated detail so tests can
// assert both the key chosen and the detail plumbed through.
const t = (key, params) => (params?.detail ? `${key}:${params.detail}` : key);

describe("formatChatError", () => {
  it("maps auth/billing/limit statuses to their specific messages", () => {
    expect(formatChatError(t, 401, "")).toBe("chat.error.sessionExpired");
    expect(formatChatError(t, 402, "")).toBe("chat.error.budgetExhausted");
    expect(formatChatError(t, 404, "")).toBe("chat.error.notFound");
    expect(formatChatError(t, 413, "")).toBe("chat.error.tooLarge");
    expect(formatChatError(t, 500, "")).toBe("chat.error.internal");
    expect(formatChatError(t, 504, "")).toBe("chat.error.timeout");
  });

  it("prefers the server detail for 403, falling back to generic", () => {
    expect(formatChatError(t, 403, "no access to this project")).toBe("no access to this project");
    expect(formatChatError(t, 403, "")).toBe("chat.error.forbidden");
  });

  it("maps 429 to quota when the detail mentions quota, rate limit otherwise", () => {
    expect(formatChatError(t, 429, "Monthly token QUOTA exceeded"))
      .toBe("chat.error.quotaReached:Monthly token QUOTA exceeded");
    expect(formatChatError(t, 429, "slow down")).toBe("chat.error.rateLimit");
    expect(formatChatError(t, 429, "")).toBe("chat.error.rateLimit");
  });

  it("maps both 502 and 503 to overloaded", () => {
    expect(formatChatError(t, 502, "")).toBe("chat.error.overloaded");
    expect(formatChatError(t, 503, "")).toBe("chat.error.overloaded");
  });

  it("includes detail on 422 when present", () => {
    expect(formatChatError(t, 422, "bad payload")).toBe("chat.error.invalidDetail:bad payload");
    expect(formatChatError(t, 422, "")).toBe("chat.error.invalid");
  });

  it("falls back to detail or generic for unknown statuses", () => {
    expect(formatChatError(t, 418, "teapot")).toBe("chat.error.default:teapot");
    expect(formatChatError(t, 418, "")).toBe("chat.error.generic");
    expect(formatChatError(t, undefined, null)).toBe("chat.error.generic");
  });
});
