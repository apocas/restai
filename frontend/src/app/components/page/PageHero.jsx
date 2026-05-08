import { Box, Typography, styled } from "@mui/material";
import { FONT_MONO, pulse, shimmer, blink, drift, sweep } from "./pageStyles";

// Reusable navy-mesh hero banner. Generalized from `dashboard/Home.jsx`'s
// `AIHero` so every CRUD/info/admin page can lead with the same look:
// gradient mesh background, optional pulsing status dot, optional mono
// stat chips, optional right-floating action buttons.
//
// Pages that want a *page identity* but no live stats can render a thin
// variant by passing `compact`. Pages that wrap a single resource (a
// project, an LLM, a user) can pass an `icon` so the title gets a glyph.

const HeroRoot = styled(Box, {
  shouldForwardProp: (p) => p !== "compact",
})(({ theme, compact }) => ({
  position: "relative",
  borderRadius: 20,
  overflow: "hidden",
  padding: compact ? theme.spacing(3, 4) : theme.spacing(4, 4.5),
  color: "#fff",
  background: `
    radial-gradient(at 20% 20%, rgba(25,118,210,0.95) 0px, transparent 55%),
    radial-gradient(at 85% 15%, rgba(14,165,233,0.90) 0px, transparent 55%),
    radial-gradient(at 75% 85%, rgba(6,182,212,0.80) 0px, transparent 55%),
    radial-gradient(at 10% 90%, rgba(56,189,248,0.70) 0px, transparent 55%),
    linear-gradient(135deg, #0b1d3a 0%, #0f2c5a 100%)
  `,
  backgroundSize: "200% 200%, 200% 200%, 200% 200%, 200% 200%, 100% 100%",
  animation: `${shimmer} 20s ease-in-out infinite`,
  [theme.breakpoints.down("md")]: { padding: theme.spacing(3) },
  // Subtle grain — same trick `AIHero` uses.
  "&::after": {
    content: '""',
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
    backgroundImage:
      "radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px)",
    backgroundSize: "4px 4px",
    mixBlendMode: "overlay",
    opacity: 0.5,
  },
}));

const StatusDot = styled(Box)(() => ({
  width: 10,
  height: 10,
  borderRadius: "50%",
  background: "#10b981",
  animation: `${pulse} 2s ease-out infinite`,
  flexShrink: 0,
}));

const StatChip = styled(Box)(() => ({
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 12px",
  borderRadius: 999,
  background: "rgba(255,255,255,0.08)",
  backdropFilter: "blur(12px)",
  border: "1px solid rgba(255,255,255,0.12)",
  fontSize: "0.78rem",
  fontWeight: 500,
  fontFamily: FONT_MONO,
  letterSpacing: "0.3px",
  whiteSpace: "nowrap",
  color: "rgba(255,255,255,0.92)",
}));

const IconWell = styled(Box)(() => ({
  position: "relative",
  width: 56,
  height: 56,
  flexShrink: 0,
  borderRadius: 16,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(255,255,255,0.08)",
  backdropFilter: "blur(12px)",
  border: "1px solid rgba(255,255,255,0.16)",
  color: "#fff",
  animation: `${drift} 6s ease-in-out infinite`,
  "& svg": { fontSize: 28 },
  // Soft cyan ring that breathes. Same colour family as the AIHero
  // gradient so it reads as part of the same surface.
  "&::after": {
    content: '""',
    position: "absolute",
    inset: -2,
    borderRadius: 18,
    border: "1px solid rgba(125,211,252,0.0)",
    animation: `${pulse} 3s ease-out infinite`,
    pointerEvents: "none",
  },
}));

// Thin cyan sweep that runs across the top edge of the hero — a subtle
// "data is flowing" cue that doesn't fight the title for attention.
const TopSweep = styled(Box)(() => ({
  position: "absolute",
  left: 0, right: 0, top: 0,
  height: 2,
  background:
    "linear-gradient(90deg, transparent, rgba(125,211,252,0.55), rgba(56,189,248,0.55), transparent)",
  animation: `${sweep} 6s ease-in-out infinite`,
  pointerEvents: "none",
  zIndex: 2,
}));

export default function PageHero({
  icon,
  eyebrow,
  title,
  subtitle,
  stats = [],
  actions,
  showStatusDot = false,
  statusLabel,
  compact = false,
  sx,
}) {
  return (
    <HeroRoot compact={compact} sx={{ mb: 3, ...sx }}>
      <TopSweep />
      <Box sx={{ position: "relative", zIndex: 1 }}>
        <Box sx={{
          display: "flex", alignItems: { xs: "flex-start", md: "center" },
          gap: 2, flexWrap: "wrap",
        }}>
          {icon && <IconWell>{icon}</IconWell>}
          <Box sx={{ flex: 1, minWidth: 240 }}>
            {eyebrow && (
              <Typography
                variant="overline"
                sx={{
                  color: "rgba(255,255,255,0.75)",
                  letterSpacing: 3,
                  fontFamily: FONT_MONO,
                  display: "block",
                  lineHeight: 1.2,
                }}
              >
                {eyebrow}
              </Typography>
            )}
            <Typography
              variant={compact ? "h5" : "h4"}
              sx={{
                mt: eyebrow ? 0.5 : 0,
                fontWeight: 700,
                letterSpacing: "-0.5px",
                color: "#fff",
                textShadow: "0 2px 20px rgba(0,0,0,0.2)",
              }}
            >
              {title}
              <Box
                component="span"
                sx={{
                  display: "inline-block",
                  width: 10,
                  ml: 0.5,
                  animation: `${blink} 1.1s steps(2, start) infinite`,
                  color: "rgba(125,211,252,0.9)",
                }}
              >
                _
              </Box>
            </Typography>
            {subtitle && (
              <Typography
                variant="body2"
                sx={{ mt: 1, color: "rgba(255,255,255,0.82)", maxWidth: 720 }}
              >
                {subtitle}
              </Typography>
            )}
          </Box>
          {actions && (
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", ml: "auto", flexWrap: "wrap" }}>
              {actions}
            </Box>
          )}
        </Box>

        {(showStatusDot || stats.length > 0) && (
          <Box sx={{ mt: 2.5, display: "flex", flexWrap: "wrap", gap: 1.25 }}>
            {showStatusDot && (
              <StatChip>
                <StatusDot />
                <span>{statusLabel || "Operational"}</span>
              </StatChip>
            )}
            {stats.map((s, i) => (
              <StatChip key={i}>
                {s.glyph && (
                  <Box component="span" sx={{ color: s.color || "#93c5fd" }}>
                    {s.glyph}
                  </Box>
                )}
                <span>{s.label}</span>
              </StatChip>
            ))}
          </Box>
        )}
      </Box>
    </HeroRoot>
  );
}
