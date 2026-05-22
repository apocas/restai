import { memo, useState, useRef } from "react";
import { Box, styled } from "@mui/material";

import useSettings from "app/hooks/useSettings";

import Brand from "app/components/Brand";
import Sidenav from "app/components/Sidenav";

import { sidenavCompactWidth, sideNavWidth } from "app/utils/constant";

// Width is CSS-driven via data-mode. `data-just-toggled="true"` briefly
// blocks the hover-expand right after a click so collapsing feels instant
// even with the cursor still inside the sidebar.
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

  '&[data-mode="compact"]': {
    width: sidenavCompactWidth,
  },
  '&[data-mode="compact"]:not([data-just-toggled="true"]):hover': {
    width: sideNavWidth,
  },

  '&[data-mode="compact"]:not(:hover) :where(.nav-label, .nav-trailing, .nav-section-tail, .nav-bullet-text, .brand-name, .brand-actions), &[data-mode="compact"][data-just-toggled="true"] :where(.nav-label, .nav-trailing, .nav-section-tail, .nav-bullet-text, .brand-name, .brand-actions)': {
    display: "none !important",
  },
  '&[data-mode="compact"]:not(:hover) .nav-section, &[data-mode="compact"][data-just-toggled="true"] .nav-section': {
    justifyContent: "center !important",
    padding: "0 !important",
    "& .nav-section-tick": { width: 14, height: 2 },
  },
  '&[data-mode="compact"]:not(:hover) .nav-item, &[data-mode="compact"][data-just-toggled="true"] .nav-item': {
    justifyContent: "center !important",
    padding: "0 !important",
    margin: "2px 8px !important",
  },
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
    // Suppress hover only when collapsing; full→compact with cursor inside
    // would otherwise re-expand. Compact→full doesn't need suppression.
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
