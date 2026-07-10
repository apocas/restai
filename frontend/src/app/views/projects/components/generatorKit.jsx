// Shared chrome for the Image + Audio generator playgrounds, so both read as
// one instrument family while each keeps its own accent + signature. Same
// forensic-lab vocabulary as the text playground (FONT_MONO eyebrows, hairline
// rules, accent rail, sweep shimmer, live pulse).
import { Box, IconButton, styled } from "@mui/material";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const HAIRLINE = "rgba(15,23,42,0.08)";

// ── The working surface: a white tile with an accent rail across the top,
// a slow sweep shimmer, and a hover glow — the same tile the text chat sits in.
export const PlaygroundTile = styled(Box, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  position: "relative",
  flex: 1,
  minHeight: 0,
  display: "flex",
  flexDirection: "column",
  borderRadius: 14,
  border: `1px solid ${HAIRLINE}`,
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.9,
    zIndex: 2,
  },
  "&::after": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    zIndex: 3,
    pointerEvents: "none",
    animation: `${sweep} 8s ease-in-out infinite`,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}14, 0 4px 10px rgba(15,23,42,0.05)`,
  },
}));

// ── Instrument header: title block on the left, controls on the right,
// a live pulse dot to say "connected", and a mono counter.
export const HeaderBar = styled(Box)({
  flex: "0 0 auto",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  flexWrap: "wrap",
  padding: "12px 16px",
  borderBottom: `1px solid ${HAIRLINE}`,
});

// ── Mono uppercase label — the type treatment that carries the lab identity.
export const Eyebrow = styled("span", {
  shouldForwardProp: (p) => p !== "accent" && p !== "muted",
})(({ accent, muted }) => ({
  fontFamily: FONT_MONO,
  fontSize: "0.66rem",
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  fontWeight: 700,
  color: muted ? "rgba(15,23,42,0.45)" : (accent || "#0f172a"),
  whiteSpace: "nowrap",
}));

// ── The result stream — scrolls internally so the tile height is fixed.
export const Stream = styled(Box)({
  flex: 1,
  minHeight: 0,
  overflow: "auto",
  padding: "20px 18px",
});

// ── The composer bar at the bottom.
export const Composer = styled(Box)({
  flex: "0 0 auto",
  display: "flex",
  alignItems: "flex-end",
  gap: 8,
  padding: "12px 14px",
  borderTop: `1px solid ${HAIRLINE}`,
  backgroundColor: "rgba(15,23,42,0.015)",
});

// Live pulse dot — reused status vocabulary.
export function PulseDot({ accent, active = false }) {
  return (
    <Box
      sx={{
        width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
        background: accent,
        boxShadow: `0 0 8px ${accent}`,
        animation: active ? `${pulse} 1.4s ease-out infinite` : "none",
        opacity: active ? 1 : 0.45,
      }}
    />
  );
}

// Primary action button — accent pill; used for Send.
export const PrimaryAction = styled(IconButton, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  width: 40, height: 40,
  color: "#fff",
  background: accent,
  borderRadius: 12,
  transition: "transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease",
  "&:hover": { background: accent, boxShadow: `0 8px 18px ${accent}55`, transform: "translateY(-1px)" },
  "&.Mui-disabled": { background: "rgba(15,23,42,0.12)", color: "#fff" },
}));

// Secondary/ghost action — upload, clear.
export const GhostAction = styled(IconButton, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  width: 40, height: 40,
  borderRadius: 12,
  color: "rgba(15,23,42,0.55)",
  border: `1px solid ${HAIRLINE}`,
  transition: "color 0.15s ease, border-color 0.15s ease, background 0.15s ease",
  "&:hover": { color: accent, borderColor: `${accent}55`, background: `${accent}0d` },
}));

// Accent-aware TextField sx — thin outline that lights to the accent on focus.
export const fieldSx = (accent) => ({
  "& .MuiOutlinedInput-root": {
    borderRadius: 12,
    fontSize: "0.9rem",
    backgroundColor: "#fff",
    "& fieldset": { borderColor: HAIRLINE },
    "&:hover fieldset": { borderColor: `${accent}66` },
    "&.Mui-focused fieldset": { borderColor: accent, borderWidth: 1 },
  },
});

export { HAIRLINE };
