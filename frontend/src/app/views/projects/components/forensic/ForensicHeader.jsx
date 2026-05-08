import { Box } from "@mui/material";
import { PALETTE, ACCENT, FONT_DISPLAY, FONT_MONO } from "./styles";

// HUD-style title row used across project tabs. Lifted from the inline
// header blocks in ProjectEditMemoryBank.jsx (lines 683-735) and
// ProjectEditMemorySearch.jsx (lines 100-123) so every tab can present the
// same icon + uppercase Chakra Petch title + mono subtitle, with an
// optional right-floating actions slot.
export default function ForensicHeader({
  icon, title, subtitle, actions, dense = false, sx,
}) {
  return (
    <Box sx={{
      display: "flex", alignItems: "center", gap: dense ? 1 : 2, flexWrap: "wrap",
      mb: dense ? 0.5 : 2,
      ...sx,
    }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        {icon && (
          <Box sx={{
            display: "flex", alignItems: "center",
            color: ACCENT,
            "& svg": {
              fontSize: 18,
              filter: `drop-shadow(0 0 6px ${ACCENT}55)`,
            },
          }}>
            {icon}
          </Box>
        )}
        <Box>
          <Box sx={{
            fontFamily: FONT_DISPLAY, fontSize: "0.95rem",
            letterSpacing: "0.18em", fontWeight: 600,
            color: PALETTE.ink, textTransform: "uppercase",
            lineHeight: 1,
          }}>
            {title}
          </Box>
          {subtitle && (
            <Box sx={{
              fontFamily: FONT_MONO, fontSize: "0.6rem",
              color: PALETTE.inkFaint, letterSpacing: "0.06em", mt: 0.25,
            }}>
              {subtitle}
            </Box>
          )}
        </Box>
      </Box>
      {actions && (
        <>
          <Box sx={{ flex: 1 }} />
          {actions}
        </>
      )}
    </Box>
  );
}
