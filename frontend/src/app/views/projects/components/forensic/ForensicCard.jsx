import { useEffect } from "react";
import { Box, Card } from "@mui/material";
import { PALETTE, ACCENT, sweep, loadFonts } from "./styles";
import ForensicHeader from "./ForensicHeader";

// Default backdrop — single radial bloom + faint blueprint grid.
// Matches ProjectEditMemorySearch.jsx (the simpler of the two memory tabs).
// Memory Bank passes its own richer plate via the `backdrop` prop.
export const DefaultBackdrop = (
  <>
    <Box sx={{
      position: "absolute", inset: 0, pointerEvents: "none",
      background: "radial-gradient(ellipse 70% 45% at 50% -10%, rgba(25,118,210,0.10), transparent 60%)",
    }}/>
    <Box sx={{
      position: "absolute", inset: 0, pointerEvents: "none", opacity: 0.6,
      backgroundImage:
        "linear-gradient(rgba(25,118,210,0.05) 1px, transparent 1px),"
      + "linear-gradient(90deg, rgba(25,118,210,0.05) 1px, transparent 1px)",
      backgroundSize: "24px 24px",
      maskImage: "radial-gradient(ellipse 80% 100% at 50% 0%, black 30%, transparent 90%)",
    }}/>
  </>
);

// Richer plate — bloom + amber bloom + grid + animated scanline.
// Identical to ProjectEditMemoryBank.jsx HUDBackdrop (lines 83-117).
// Exported so the bank can keep its existing visual exactly.
export const RichBackdrop = (
  <>
    <Box sx={{
      position: "absolute", inset: 0, pointerEvents: "none",
      background: "radial-gradient(ellipse 70% 45% at 50% -10%, rgba(25,118,210,0.10), transparent 60%)",
    }}/>
    {/* Warm amber bloom from bottom-right (theme secondary) */}
    <Box sx={{
      position: "absolute", inset: 0, pointerEvents: "none",
      background: "radial-gradient(ellipse 50% 35% at 90% 110%, rgba(245,158,11,0.07), transparent 60%)",
    }}/>
    {/* Faint blueprint grid */}
    <Box sx={{
      position: "absolute", inset: 0, pointerEvents: "none", opacity: 0.7,
      backgroundImage:
        "linear-gradient(rgba(25,118,210,0.05) 1px, transparent 1px),"
      + "linear-gradient(90deg, rgba(25,118,210,0.05) 1px, transparent 1px)",
      backgroundSize: "24px 24px",
      maskImage: "radial-gradient(ellipse 80% 100% at 50% 0%, black 30%, transparent 90%)",
    }}/>
    {/* Animated scanline */}
    <Box sx={{
      position: "absolute", left: 0, right: 0, top: 0, bottom: 0,
      pointerEvents: "none", overflow: "hidden", zIndex: 0,
    }}>
      <Box sx={{
        position: "absolute", left: 0, right: 0, height: 2,
        background: "linear-gradient(90deg, transparent, rgba(25,118,210,0.32), transparent)",
        animation: `${sweep} 7s linear infinite`,
        top: "12%",
      }}/>
    </Box>
  </>
);

// Outer plate every project tab uses. Renders a void-bg Card with a faint
// blue hairline border, the chosen backdrop (default = simple bloom + grid),
// then a header + body slot.
//
// Pass `title={null}` to omit the header entirely (used by ProjectTabNav,
// which is just a list of buttons — no need for an icon + title).
export default function ForensicCard({
  icon, title, subtitle, actions, headerSx,
  backdrop = DefaultBackdrop,
  children, sx, dense = false,
}) {
  useEffect(() => { loadFonts(); }, []);

  return (
    <Card
      elevation={0}
      sx={{
        position: "relative",
        background: PALETTE.void,
        border: `1px solid ${PALETTE.edge}`,
        borderRadius: 1,
        overflow: "hidden",
        color: PALETTE.ink,
        p: { xs: 2, md: 3 },
        boxShadow: "0 1px 0 rgba(255,255,255,0.9) inset, 0 8px 32px rgba(34,42,69,0.06)",
        ...sx,
      }}
    >
      {backdrop}
      <Box sx={{ position: "relative", zIndex: 1 }}>
        {title && (
          <ForensicHeader
            icon={icon} title={title} subtitle={subtitle}
            actions={actions} dense={dense} sx={headerSx}
          />
        )}
        {children}
      </Box>
    </Card>
  );
}

export { ACCENT, PALETTE };
