// Client-side bounds mirroring Pydantic Field constraints on
// restai.models.models.ProjectOptions. Guards ship feedback to the
// user before hitting the network so a typo doesn't cost a 422
// round-trip. Server remains the source of truth — these are UX sugar.

export const clientValidators = {
  rate_limit: (v) => {
    if (v == null || v === "") return "";
    const n = Number(v);
    if (!Number.isFinite(n) || n < 1 || n > 10000)
      return "Rate limit must be between 1 and 10000 (or empty for unlimited).";
    return "";
  },
  k: (v) => {
    if (v == null || v === "") return "";
    const n = Number(v);
    if (!Number.isFinite(n) || n < 1) return "k must be ≥ 1.";
    return "";
  },
  score: (v) => {
    if (v == null || v === "") return "";
    const n = Number(v);
    if (!Number.isFinite(n) || n < 0 || n > 1) return "Score must be between 0.0 and 1.0.";
    return "";
  },
  memory_bank_max_tokens: (v) => {
    if (v == null || v === "") return "";
    const n = Number(v);
    if (!Number.isFinite(n) || n < 200 || n > 10000)
      return "Token budget must be between 200 and 10000.";
    return "";
  },
  cache_threshold: (v) => {
    if (v == null || v === "") return "";
    const n = Number(v);
    if (!Number.isFinite(n) || n < 0 || n > 1) return "Threshold must be between 0.0 and 1.0.";
    return "";
  },
};

// Combined lookup: server error wins over client validator so the
// backend's authoritative message is what the user sees once a save
// has been attempted.
export function makeErrorFor(fieldErrors, state) {
  return (name) => {
    const server = (fieldErrors && (fieldErrors[name] || fieldErrors[`options.${name}`])) || "";
    if (server) return server;
    const validator = clientValidators[name];
    if (validator) return validator(state?.options?.[name]);
    return "";
  };
}
