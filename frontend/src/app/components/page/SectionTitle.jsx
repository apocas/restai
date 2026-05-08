import { Box, Typography, Divider } from "@mui/material";
import { FONT_MONO, pulse } from "./pageStyles";

// Section header for clean cards. Lifted from `dashboard/Home.jsx`'s
// inline `SectionTitle` so every page can group sections with the same
// uppercase label + divider treatment.
//
// Adds a small pulsing accent dot on the left so the header reads as
// "live channel" rather than a static h6. Optional right-side `actions`
// slot for "view all" links / refresh buttons.
export default function SectionTitle({ children, actions, accent = "#22c55e", sx }) {
  return (
    <Box sx={{ mb: 2, mt: 1, ...sx }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <Box
          sx={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: accent,
            animation: `${pulse} 2.5s ease-out infinite`,
            flexShrink: 0,
          }}
        />
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{
            fontWeight: 600,
            letterSpacing: 1.5,
            lineHeight: 1.2,
            fontFamily: FONT_MONO,
          }}
        >
          {children}
        </Typography>
        {actions && (
          <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 1 }}>
            {actions}
          </Box>
        )}
      </Box>
      <Divider sx={{ borderColor: "divider", opacity: 0.7 }} />
    </Box>
  );
}
