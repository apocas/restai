import { NavLink } from "react-router-dom";
import { Box, Icon, styled } from "@mui/material";

import MatxVerticalNavExpansionPanel from "./MatxVerticalNavExpansionPanel";

// Sky accent — same family as the rest of the modernised app.
const ACCENT = "#38bdf8";
const ACCENT_SOFT = "rgba(56,189,248,0.10)";

// ── Section heading row (Backend, Admin, etc.). The data-mode rules
// in Layout1Sidenav collapse this to just the tick in compact mode.
const SectionRow = styled("div")(() => ({
  display: "flex",
  alignItems: "center",
  gap: 8,
  marginTop: 22,
  marginBottom: 8,
  marginLeft: 4,
  marginRight: 4,
  paddingLeft: 12,
  paddingRight: 12,
}));
const SectionTick = styled("div")(() => ({
  width: 12,
  height: 2,
  background: ACCENT,
  flexShrink: 0,
}));
const SectionLabel = styled("span")(() => ({
  fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
  fontSize: 10,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  fontWeight: 800,
  color: "rgba(186,230,253,0.72)",
  whiteSpace: "nowrap",
}));
const SectionTail = styled("div")(() => ({
  flex: 1,
  height: 1,
  background: "linear-gradient(90deg, rgba(56,189,248,0.18), transparent)",
}));

// ── Shared item shape — a single-tier flex row.
//
// Used directly for external links (`<a>`), and as a styled wrapper
// for `NavLink` (internal). Both render identically so the icon/label
// alignment is the same regardless of item kind.
const itemBaseSx = {
  position: "relative",
  display: "flex",
  alignItems: "center",
  height: 40,
  marginLeft: 6,
  marginRight: 6,
  marginBottom: 4,
  paddingLeft: 14,
  paddingRight: 14,
  borderRadius: "6px",
  cursor: "pointer",
  color: "rgba(255,255,255,0.78)",
  textDecoration: "none",
  transition: "all 160ms cubic-bezier(0.4, 0, 0.2, 1)",
  whiteSpace: "nowrap",
  overflow: "hidden",
  // Left-edge sky rail — fades in on hover/active.
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, top: 0, bottom: 0,
    width: 3,
    background: ACCENT,
    opacity: 0,
    transform: "scaleY(0.6)",
    transformOrigin: "center",
    transition: "opacity 160ms, transform 160ms",
  },
  "&:hover": {
    background: "rgba(255,255,255,0.04)",
    color: "#ffffff",
    "&::before": { opacity: 0.6, transform: "scaleY(1)" },
    "& .nav-icon": { color: ACCENT },
  },
  "&.active": {
    background: ACCENT_SOFT,
    color: "#ffffff",
    "&::before": { opacity: 1, transform: "scaleY(1)" },
    "& .nav-icon": { color: ACCENT },
    "& .nav-label": { fontWeight: 700, color: "#ffffff" },
  },
};

const ExternalItem = styled("a")(() => itemBaseSx);
const InternalItem = styled(NavLink)(() => itemBaseSx);

const NavIcon = styled("span")(() => ({
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 18,
  height: 18,
  flexShrink: 0,
  fontSize: 18,
  color: "rgba(255,255,255,0.78)",
  transition: "color 160ms",
  "& .MuiIcon-root": { fontSize: 18, lineHeight: 1 },
}));

const NavBullet = styled("div")(() => ({
  width: 5,
  height: 5,
  borderRadius: "50%",
  background: "rgba(186,230,253,0.55)",
  flexShrink: 0,
}));

const NavLabel = styled("span")(() => ({
  fontSize: "0.84rem",
  letterSpacing: "0.01em",
  marginLeft: 14,
  flex: 1,
  minWidth: 0,
  overflow: "hidden",
  textOverflow: "ellipsis",
}));

const NavBadge = styled("span")(() => ({
  marginLeft: 8,
  padding: "1px 8px",
  fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
  fontSize: "0.62rem",
  fontWeight: 800,
  letterSpacing: "0.04em",
  borderRadius: 4,
  background: ACCENT_SOFT,
  color: ACCENT,
  border: `1px solid ${ACCENT}33`,
  flexShrink: 0,
}));

function ItemBody({ item }) {
  return (
    <>
      <NavIcon className="nav-icon">
        {item.icon
          ? <Icon>{item.icon}</Icon>
          : item.iconText
            ? <span className="nav-bullet-text">{item.iconText}</span>
            : <NavBullet />}
      </NavIcon>
      <NavLabel className="nav-label">{item.name}</NavLabel>
      {item.badge && (
        <NavBadge className="nav-trailing">{item.badge.value}</NavBadge>
      )}
    </>
  );
}

export default function MatxVerticalNav({ items }) {
  const renderLevels = (data) =>
    data.map((item, index) => {
      // Section heading
      if (item.type === "label") {
        return (
          <SectionRow key={index} className="nav-section">
            <SectionTick className="nav-section-tick" />
            <SectionLabel className="nav-label">{item.label}</SectionLabel>
            <SectionTail className="nav-section-tail" />
          </SectionRow>
        );
      }
      // Parent with submenu
      if (item.children) {
        return (
          <MatxVerticalNavExpansionPanel item={item} key={index}>
            {renderLevels(item.children)}
          </MatxVerticalNavExpansionPanel>
        );
      }
      // External link
      if (item.type === "extLink") {
        return (
          <ExternalItem
            key={index}
            className="nav-item"
            href={item.path}
            rel="noopener noreferrer"
            target="_blank"
          >
            <ItemBody item={item} />
          </ExternalItem>
        );
      }
      // Internal nav link
      return (
        <InternalItem
          key={index}
          to={item.path}
          className={({ isActive }) => (isActive ? "active nav-item" : "nav-item")}
        >
          <ItemBody item={item} />
        </InternalItem>
      );
    });

  return (
    <Box sx={{ position: "relative", zIndex: 1, pt: 1 }}>
      {renderLevels(items)}
    </Box>
  );
}
