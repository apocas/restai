import { memo, useState, useRef } from "react";
import { Box, styled } from "@mui/material";

import useSettings from "app/hooks/useSettings";

import Brand from "app/components/Brand";
import Sidenav from "app/components/Sidenav";

import { sidenavCompactWidth, sideNavWidth } from "app/utils/constant";

// Sidebar root — width is purely CSS-driven from the data-mode attribute.
// `data-mode="compact"` shrinks to 80px and a CSS :hover rule expands
// back to 260 (so labels reveal). `data-just-toggled="true"` is a brief
// gate set right after the user clicks the toggle, so the click feels
// instant even if the cursor is still inside the sidebar.
//
// All label / chevron / badge visibility is also CSS-driven via the
// same data attributes — every nav item has classes like .nav-label
// and .nav-trailing that the root selectors hide / show.
const SidebarRoot = styled(Box)(() => ({
  position: "fixed",
  top: 0,
  left: 0,
  height: "100vh",
  width: sideNavWidth,
  zIndex: 111,
  overflow: "hidden",
  color: "rgba(255,255,255,0.85)",
  transition: "width 220ms cubic-bezier(0.4, 0, 0.2, 1)",
  backgroundColor: "#0b1220",
  backgroundImage: `
    radial-gradient(at 0% 0%, rgba(2,132,199,0.22) 0px, transparent 45%),
    radial-gradient(at 100% 100%, rgba(8,145,178,0.18) 0px, transparent 50%),
    radial-gradient(at 50% 60%, rgba(99,102,241,0.10) 0px, transparent 55%)
  `,
  borderRight: "1px solid rgba(255,255,255,0.06)",
  boxShadow: "4px 0 24px rgba(0,0,0,0.18)",
  // Faint grain so the gradient doesn't feel like a Stripe login.
  "&::after": {
    content: '""',
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
    backgroundImage:
      "radial-gradient(rgba(255,255,255,0.025) 1px, transparent 1px)",
    backgroundSize: "4px 4px",
    mixBlendMode: "overlay",
    opacity: 0.6,
  },

  // ── Compact mode ────────────────────────────────────────────
  '&[data-mode="compact"]': {
    width: sidenavCompactWidth,
  },
  // Hover-expand (only when not freshly toggled).
  '&[data-mode="compact"]:not([data-just-toggled="true"]):hover': {
    width: sideNavWidth,
  },

  // Hide chrome when in compact mode AND (not hovered OR just-toggled).
  // The :where selector is just a syntactic shortcut so the long
  // condition chain stays readable.
  '&[data-mode="compact"]:not(:hover) :where(.nav-label, .nav-trailing, .nav-section-tail, .nav-bullet-text, .brand-name, .brand-actions), &[data-mode="compact"][data-just-toggled="true"] :where(.nav-label, .nav-trailing, .nav-section-tail, .nav-bullet-text, .brand-name, .brand-actions)': {
    display: "none !important",
  },
  // Section labels collapse to a centred 14×2 tick.
  '&[data-mode="compact"]:not(:hover) .nav-section, &[data-mode="compact"][data-just-toggled="true"] .nav-section': {
    justifyContent: "center !important",
    padding: "0 !important",
    "& .nav-section-tick": { width: 14, height: 2 },
  },
  // Nav items: drop margins/padding and centre icons in the 80-px column.
  '&[data-mode="compact"]:not(:hover) .nav-item, &[data-mode="compact"][data-just-toggled="true"] .nav-item': {
    justifyContent: "center !important",
    padding: "0 !important",
    margin: "2px 8px !important",
  },
  // Brand collapses to just the logo, centred.
  '&[data-mode="compact"]:not(:hover) .brand-root, &[data-mode="compact"][data-just-toggled="true"] .brand-root': {
    justifyContent: "center !important",
    padding: "20px 0 18px !important",
  },
}));

const NavListBox = styled(Box)({
  height: "100%",
  display: "flex",
  flexDirection: "column",
});

const Layout1Sidenav = () => {
  const { settings, updateSettings } = useSettings();
  const leftSidebar = settings.layout1Settings.leftSidebar;
  const isCompact = leftSidebar.mode === "compact";

  // After clicking toggle, the mouse is still inside the sidebar — so
  // the :hover rule would fire and the sidebar would *appear* not to
  // collapse. The `justToggled` flag suppresses :hover until the
  // cursor leaves; on mouseleave we reset it and hover-expand resumes
  // normally on the next entry.
  const [justToggled, setJustToggled] = useState(false);
  const lockRef = useRef(false);

  const handleToggle = () => {
    const goingToCompact = !isCompact;
    // Suppress hover-expand only when collapsing — full→compact with
    // the cursor still inside the sidebar would otherwise re-expand.
    // Compact→full doesn't need suppression (sidebar's expanding anyway).
    if (goingToCompact) {
      lockRef.current = true;
      setJustToggled(true);
    }
    updateSettings({
      layout1Settings: {
        leftSidebar: { ...leftSidebar, mode: goingToCompact ? "compact" : "full" },
      },
    });
  };

  const handleMouseLeave = () => {
    if (lockRef.current) {
      lockRef.current = false;
      setJustToggled(false);
    }
  };

  return (
    <SidebarRoot
      data-mode={isCompact ? "compact" : "full"}
      data-just-toggled={justToggled ? "true" : "false"}
      onMouseLeave={handleMouseLeave}
    >
      <NavListBox>
        <Brand onToggleSidenav={handleToggle} />
        <Sidenav />
      </NavListBox>
    </SidebarRoot>
  );
};

export default memo(Layout1Sidenav);
