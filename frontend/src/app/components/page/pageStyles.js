// Shared visual tokens for the modern page-shell aesthetic. Lifted from
// `dashboard/Home.jsx` (chartCardSx + AIHero gradient) so every CRUD/info
// surface in the app reads as the same family — clean white cards over a
// neutral background, with a navy/cyan gradient hero per page.
//
// Memory Bank + Memory Search keep the older forensic-deck look — they're
// dedicated data inspectors and the high-density palette helps. For
// everything else, use this kit.

import { keyframes } from "@emotion/react";

// Fonts — same stack the AIHero already uses, kept here so any page that
// wants tabular numbers can reach for a single token.
export const FONT_MONO = '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace';

// Plain card. Same shape as Home.jsx's `chartCardSx`. Use this whenever a
// page section needs to be visually grouped — list shells, edit forms,
// sidebar nav, comments, anything.
//
// Subtle hover lift + animated accent line at the top so cards feel
// "alive" without being noisy. The accent line is a thin cyan→blue
// sweep that runs once per second (mostly dormant) — drops a heartbeat
// signal that says "this is a connected, breathing thing".
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

// Variant: same look, no padding. For list pages where the inner table
// owns its own edges (avoids double-padding around the toolbar).
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

// Keyframes copied from AIHero so any page-level component can reuse the
// same pulse / shimmer behaviour without re-declaring them.
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

// Faint horizontal sweep — sits at the top edge of a card and runs once
// every few seconds. Cyan → transparent. Drops a "this surface is wired
// up" heartbeat without grabbing attention.
export const sweep = keyframes`
  0%   { transform: translateX(-100%); opacity: 0; }
  20%  { opacity: 1; }
  80%  { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0; }
`;

// One-off blink for cursor glyphs. Same cadence the AIHero uses.
export const blink = keyframes`
  50% { opacity: 0; }
`;

// Soft ambient drift — used by hero/icon decorations.
export const drift = keyframes`
  0%   { transform: translateY(0); }
  50%  { transform: translateY(-3px); }
  100% { transform: translateY(0); }
`;

// Migration shim — old `forensicCardSx` callers re-routed here. Keeping
// the alias means we can switch every page off the bluish forensic
// plate to the clean MUI card with a single sed rename, without having
// to touch each file's prop wiring.
export { cleanCardSx as forensicCardSx };

// Compat export so files that still import `loadFonts` from here don't
// crash. The clean kit doesn't need a font preload (regular MUI fonts
// are already in the page), so this is a no-op.
export const loadFonts = () => {};
