// Maps chat HTTP failures to user-facing messages. Called from both the
// streaming and non-streaming error paths in ChatPanel so messaging is
// consistent regardless of transport. Kept dependency-free so it can be
// unit-tested without pulling in the ChatPanel component tree.
export function formatChatError(t, status, detail) {
  const d = (detail || "").toString().trim();
  switch (status) {
    case 401: return t("chat.error.sessionExpired");
    case 402: return t("chat.error.budgetExhausted");
    case 403: return d || t("chat.error.forbidden");
    case 404: return t("chat.error.notFound");
    case 413: return t("chat.error.tooLarge");
    case 422: return d ? t("chat.error.invalidDetail", { detail: d }) : t("chat.error.invalid");
    case 429:
      if (d && d.toLowerCase().includes("quota"))
        return t("chat.error.quotaReached", { detail: d });
      return t("chat.error.rateLimit");
    case 500: return t("chat.error.internal");
    case 502:
    case 503:
      return t("chat.error.overloaded");
    case 504: return t("chat.error.timeout");
    default:
      if (d) return t("chat.error.default", { detail: d });
      return t("chat.error.generic");
  }
}
