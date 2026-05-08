import { Card, Box, Typography } from "@mui/material";
import { cleanCardSx, FONT_MONO } from "./pageStyles";
import SectionTitle from "./SectionTitle";

// Clean replacement for the old `<ForensicCard>` wrapper on non-memory
// surfaces. Matches the ForensicCard API (icon, title, subtitle, actions,
// children) so files can swap by renaming the import — but renders a
// plain dashboard-style white card without the bluish void plate.
//
// When `title` is omitted, it just renders an empty padded card. When
// `eyebrow` is also passed, the header gets the same treatment as a
// PageHero — `EYEBROW` overline + `Title` heading + optional subtitle —
// so a per-tab card and the page hero share the same vocabulary.
export default function ContentCard({
  icon,
  title,
  subtitle,
  eyebrow,
  actions,
  children,
  sx,
  bodyPadding = true,
}) {
  const hasHeader = !!(title || eyebrow || actions);
  return (
    <Card
      elevation={0}
      sx={{
        ...cleanCardSx,
        p: 0,
        ...sx,
      }}
    >
      {hasHeader && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 2,
            flexWrap: "wrap",
            px: 3,
            pt: 2.5,
            pb: hasHeader && bodyPadding ? 2 : 1.5,
            borderBottom: "1px solid",
            borderColor: "divider",
          }}
        >
          {icon && (
            <Box
              sx={{
                width: 40,
                height: 40,
                flexShrink: 0,
                borderRadius: 2,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: "rgba(25,118,210,0.08)",
                color: "primary.main",
                "& svg": { fontSize: 22 },
              }}
            >
              {icon}
            </Box>
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {eyebrow && (
              <Typography
                variant="overline"
                sx={{
                  color: "text.secondary",
                  letterSpacing: 1.5,
                  fontFamily: FONT_MONO,
                  display: "block",
                  lineHeight: 1.2,
                  fontSize: "0.65rem",
                }}
              >
                {eyebrow}
              </Typography>
            )}
            {title && (
              <Typography
                variant="h6"
                sx={{ fontWeight: 700, lineHeight: 1.2, mt: eyebrow ? 0.25 : 0 }}
              >
                {title}
              </Typography>
            )}
            {subtitle && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ mt: 0.5 }}
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
      )}
      <Box sx={{ p: bodyPadding ? 3 : 0 }}>{children}</Box>
    </Card>
  );
}

export { SectionTitle };
