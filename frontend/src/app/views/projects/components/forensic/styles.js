// Shared visual tokens for the project pages' "forensic command deck" look.

import { keyframes } from "@emotion/react";

// Paper-white base with cool blue tint, faint blue hairline, theme-primary
// ink. Tuned for legibility on white surfaces with restrained contrast.
export const PALETTE = {
  void:     "#f4f7fb",
  surface:  "rgba(255, 255, 255, 0.78)",
  edge:     "rgba(25, 118, 210, 0.18)",
  ink:      "#222a45",
  inkDim:   "rgba(34, 42, 69, 0.62)",
  inkFaint: "rgba(34, 42, 69, 0.36)",
};

export const ACCENT      = "#1976d2";  // theme blue primary
export const ACCENT_SOFT = "#64b5f6";  // blue-300 — softer washes

export const FONT_DISPLAY = "'Chakra Petch', ui-sans-serif, system-ui, sans-serif";
export const FONT_MONO    = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace";

// `forensicCardSx` aliases the clean MUI card look used by the dashboard.
// The bluish plate is still available to Memory Bank / Memory Search via
// the <ForensicCard> wrapper component.
export { cleanCardSx as forensicCardSx } from "app/components/page/pageStyles";

// Idempotent font-link injector. ForensicCard calls it on mount so any
// tab that uses the kit gets the right typography without remembering
// to import it themselves.
const FONTS_LINK_ID = "forensic-fonts";
export function loadFonts() {
  if (typeof document === "undefined") return;
  if (document.getElementById(FONTS_LINK_ID)) return;
  const link = document.createElement("link");
  link.id = FONTS_LINK_ID;
  link.rel = "stylesheet";
  link.href = "https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap";
  document.head.appendChild(link);
}

// Animations — exported for the few surfaces that want ambient motion
// (Memory Bank's focused shard, dot pulse). Most tabs won't import these.
export const breath = keyframes`
  0%,100% { box-shadow: 0 0 18px rgba(25,118,210,0.08), inset 0 0 24px rgba(25,118,210,0.03); }
  50%     { box-shadow: 0 0 36px rgba(25,118,210,0.20), inset 0 0 32px rgba(25,118,210,0.06); }
`;
export const drift = keyframes`
  0%   { transform: translate3d(0,0,0); }
  50%  { transform: translate3d(0,-2px,0); }
  100% { transform: translate3d(0,0,0); }
`;
export const sweep = keyframes`
  0%   { transform: translateX(-100%); opacity: 0; }
  50%  { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0; }
`;
export const tickerIn = keyframes`
  from { opacity: 0; transform: translateY(8px); filter: blur(6px); }
  to   { opacity: 1; transform: translateY(0);    filter: blur(0); }
`;
