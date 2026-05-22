// Shared visual tokens for the modern page-shell aesthetic. Lifted from
// dashboard/Home.jsx so every CRUD/info surface reads as the same family.
// Memory Bank + Memory Search keep the forensic-deck look — high-density.

import { keyframes } from "@emotion/react";

export const FONT_MONO = '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace';

export const cleanCardSx = {
  position: "relative",
  p: 2.5,
  borderRadius: 3,
  border: "1px solid",
  borderColor: "divider",
  backgroundColor: "background.paper",
  transition: "transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease",
  overflow: "hidden",
  "&:hover": {
    transform: "translateY(-2px)",
    borderColor: "rgba(25,118,210,0.35)",
    boxShadow: "0 12px 28px rgba(15,23,42,0.06), 0 2px 6px rgba(15,23,42,0.04)",
  },
};

// No padding so the inner table can own its edges (no double-padding).
export const cleanCardFlushSx = {
  position: "relative",
  borderRadius: 3,
  border: "1px solid",
  borderColor: "divider",
  backgroundColor: "background.paper",
  overflow: "hidden",
  transition: "transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease",
  "&:hover": {
    borderColor: "rgba(25,118,210,0.35)",
    boxShadow: "0 12px 28px rgba(15,23,42,0.06), 0 2px 6px rgba(15,23,42,0.04)",
  },
};

export const pulse = keyframes`
  0%   { box-shadow: 0 0 0 0 rgba(16,185,129,0.55); }
  70%  { box-shadow: 0 0 0 10px rgba(16,185,129,0); }
  100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
`;

export const shimmer = keyframes`
  0%   { background-position:   0% 50%; }
  50%  { background-position: 100% 50%; }
  100% { background-position:   0% 50%; }
`;

export const sweep = keyframes`
  0%   { transform: translateX(-100%); opacity: 0; }
  20%  { opacity: 1; }
  80%  { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0; }
`;

export const blink = keyframes`
  50% { opacity: 0; }
`;

export const drift = keyframes`
  0%   { transform: translateY(0); }
  50%  { transform: translateY(-3px); }
  100% { transform: translateY(0); }
`;

// Alias kept so all callers migrate from the forensic plate via one sed.
export { cleanCardSx as forensicCardSx };

// No-op compat shim — clean kit doesn't need preloaded fonts.
export const loadFonts = () => {};
