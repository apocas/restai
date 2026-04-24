// Centralized semantic color tokens. Use these instead of literal hex
// codes scattered across views — keeps status/role colors consistent
// and gives one place to retune (or wire to a future dark-mode token
// system) when design changes.
//
// Each value is the same hex literal previously inlined in views, so
// migrating call-sites is purely visual-equivalent.

export const colors = {
  status: {
    success: "#10b981", // green — healthy / public / configured
    warning: "#f59e0b", // amber — restricted / partial / mid-strength
    error:   "#ef4444", // red — admin / private / weak / disabled
    info:    "#6366f1", // indigo — informational accents (team admin, locks)
    muted:   "#6b7280", // gray — neutral / member / unknown
  },
  role: {
    platformAdmin: "#ef4444",
    teamAdmin:     "#6366f1",
    member:        "#6b7280",
  },
};

// rgba helpers for badge backgrounds — kept inline since they always
// wrap one of the role/status colors above.
export const rgba = {
  platformAdmin: "rgba(239, 68, 68, 0.12)",
  teamAdmin:     "rgba(99, 102, 241, 0.12)",
  member:        "rgba(107, 114, 128, 0.15)",
};
