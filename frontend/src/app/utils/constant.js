export const topBarHeight = 64;
export const sideNavWidth = 260;
export const navbarHeight = 60;
export const sidenavCompactWidth = 80;
export const containedLayoutWidth = 1200;

// Per-type accent palette. `bg` is the chip background tint; `color` is
// the chip text + the rail/glow accent on the project library card.
// Cyan was added for the new "app" type so it slots into the AI-mesh
// hero language without a hot red fallback.
export const PROJECT_TYPE_COLORS = {
  rag:   { bg: "rgba(99,102,241,0.12)", color: "#6366f1" },  // indigo-500
  agent: { bg: "rgba(16,185,129,0.12)", color: "#10b981" },  // emerald-500
  block: { bg: "rgba(107,114,128,0.15)", color: "#6b7280" },  // gray-500
  app:   { bg: "rgba(8,145,178,0.12)",  color: "#0891b2" },  // cyan-600
};
