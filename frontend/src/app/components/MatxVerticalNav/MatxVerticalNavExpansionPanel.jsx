import { useCallback, useEffect, useRef, useState } from "react";
import { Icon, styled } from "@mui/material";
import { ChevronRight } from "@mui/icons-material";
import { useLocation } from "react-router-dom";

const ACCENT = "#38bdf8";
const ACCENT_SOFT = "rgba(56,189,248,0.10)";

// Same item shape as MatxVerticalNav.ItemBase so flat items and
// expansion-panel parents align identically. The only differences are
// it's a clickable <button> (rather than a link) and it carries an
// `.open` style for the expanded state.
const ParentRow = styled("div")(() => ({
  position: "relative",
  display: "flex",
  alignItems: "center",
  height: 40,
  marginLeft: 6,
  marginRight: 6,
  marginBottom: 4,
  paddingLeft: 14,
  paddingRight: 14,
  borderRadius: 6,
  cursor: "pointer",
  color: "rgba(255,255,255,0.78)",
  transition: "all 160ms cubic-bezier(0.4, 0, 0.2, 1)",
  whiteSpace: "nowrap",
  overflow: "hidden",
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
  "&.open": {
    background: ACCENT_SOFT,
    color: "#ffffff",
    "&::before": { opacity: 1, transform: "scaleY(1)" },
    "& .nav-icon": { color: ACCENT },
    "& .nav-label": { fontWeight: 700, color: "#ffffff" },
  },
}));

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

const Chevron = styled("span")(() => ({
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  marginLeft: 4,
  flexShrink: 0,
  transition: "transform 200ms cubic-bezier(0, 0, 0.2, 1)",
  color: "rgba(186,230,253,0.45)",
  "&.open": { transform: "rotate(90deg)", color: ACCENT },
}));

const Submenu = styled("div")(() => ({
  overflow: "hidden",
  transition: "max-height 0.3s cubic-bezier(0, 0, 0.2, 1)",
}));

export default function MatxVerticalNavExpansionPanel({ item, children }) {
  const [collapsed, setCollapsed] = useState(true);
  const ref = useRef(null);
  const heightRef = useRef(0);
  const { pathname } = useLocation();
  const { name, icon, iconText, badge } = item;

  const calcHeight = useCallback((node) => {
    if (!node) return;
    if (node.dataset?.role === "submenu-child") {
      heightRef.current += node.scrollHeight;
    } else {
      heightRef.current += 44;
    }
    if (!node.dataset || node.dataset.role !== "submenu-child") {
      for (const child of node.children) calcHeight(child);
    }
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    heightRef.current = 0;
    calcHeight(ref.current);
    for (const child of ref.current.children) {
      if (child.getAttribute && child.getAttribute("href") === pathname) {
        setCollapsed(false);
      }
    }
  }, [pathname, calcHeight]);

  const handleClick = () => {
    heightRef.current = 0;
    if (ref.current) calcHeight(ref.current);
    setCollapsed((c) => !c);
  };

  return (
    <div>
      <ParentRow
        className={`nav-item ${!collapsed ? "open" : ""}`.trim()}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleClick(); }}
      >
        <NavIcon className="nav-icon">
          {icon
            ? <Icon>{icon}</Icon>
            : iconText
              ? <span className="nav-bullet-text">{iconText}</span>
              : <NavBullet />}
        </NavIcon>
        <NavLabel className="nav-label">{name}</NavLabel>
        {badge && <NavBadge className="nav-trailing">{badge.value}</NavBadge>}
        <Chevron className={`nav-trailing ${!collapsed ? "open" : ""}`.trim()}>
          <ChevronRight fontSize="small" />
        </Chevron>
      </ParentRow>

      <Submenu
        ref={ref}
        style={{ maxHeight: collapsed ? 0 : heightRef.current }}
        data-role="submenu"
      >
        {children}
      </Submenu>
    </div>
  );
}
