import { Fragment, useState } from "react";
import {
  Box,
  Card,
  Drawer,
  IconButton,
  useMediaQuery,
  styled,
} from "@mui/material";
import { Menu as MenuIcon } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import { FONT_MONO } from "app/components/page/pageStyles";

// Sky accent — same family as the modernised user info / sidebar nav.
const ACCENT = "#0284c7";        // sky-700, matches projects' navy/cyan family
const ACCENT_SOFT = "rgba(2,132,199,0.10)";

// ── Card chrome with sky accent rail.
const NavCard = styled(Card)(() => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: ACCENT,
    opacity: 0.85,
    pointerEvents: "none",
  },
}));

// Section label — uppercase mono with a sky tick rule.
const NavSectionLabel = styled("div")(() => ({
  display: "flex",
  alignItems: "center",
  gap: 8,
  paddingLeft: 14,
  paddingRight: 14,
  marginTop: 14,
  marginBottom: 4,
  "&::before": {
    content: '""',
    width: 10,
    height: 2,
    background: ACCENT,
    flexShrink: 0,
  },
  "& > span": {
    fontFamily: FONT_MONO,
    fontSize: 10,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
    fontWeight: 800,
    color: "rgba(15,23,42,0.55)",
  },
}));

// Single-row tab — sky rail on hover/active, mono icon recolour. Same
// vocabulary as the modernised user-info nav so the two sidebars
// visually rhyme.
const NavItem = styled("button", {
  shouldForwardProp: (p) => p !== "active",
})(({ active }) => ({
  position: "relative",
  display: "flex",
  alignItems: "center",
  gap: 10,
  width: "calc(100% - 12px)",
  marginLeft: 6,
  marginRight: 6,
  marginBottom: 2,
  height: 36,
  paddingLeft: 14,
  paddingRight: 14,
  border: "none",
  borderRadius: 6,
  backgroundColor: active ? ACCENT_SOFT : "transparent",
  color: active ? ACCENT : "rgba(15,23,42,0.78)",
  cursor: "pointer",
  fontSize: "0.84rem",
  fontWeight: active ? 700 : 500,
  textAlign: "left",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
  transition: "all 160ms cubic-bezier(0.4, 0, 0.2, 1)",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, top: 0, bottom: 0,
    width: 3,
    background: ACCENT,
    opacity: active ? 1 : 0,
    transform: active ? "scaleY(1)" : "scaleY(0.6)",
    transition: "opacity 160ms, transform 160ms",
  },
  "&:hover": {
    backgroundColor: active ? ACCENT_SOFT : "rgba(15,23,42,0.04)",
    color: ACCENT,
    "&::before": { opacity: active ? 1 : 0.6, transform: "scaleY(1)" },
    "& .nav-icon": { color: ACCENT },
  },
  "& .nav-icon": {
    fontSize: 17,
    flexShrink: 0,
    transition: "color 160ms",
    color: active ? ACCENT : "rgba(15,23,42,0.55)",
  },
}));

// Section labels per group key. English fallbacks; translate via
// projects.tabnav.* later if needed.
const SECTION_META = {
  build:   { label: "Build" },
  operate: { label: "Operate" },
  engage:  { label: "Engage" },
};

export default function ProjectTabNav({ tabs, active, setActive }) {
  const { t } = useTranslation();
  const [openDrawer, setOpenDrawer] = useState(false);
  const downMd = useMediaQuery((theme) => theme.breakpoints.down("md"));

  // Group tabs by section in source order. Tabs without a section land
  // under "build" (sane default — e.g. the first tab is always General).
  const grouped = [];
  const seen = new Set();
  tabs.forEach((tab) => {
    const sec = tab.section || "build";
    if (!seen.has(sec)) {
      seen.add(sec);
      grouped.push({ key: sec, items: [] });
    }
    grouped.find((g) => g.key === sec).items.push(tab);
  });

  function TabListContent() {
    return (
      <Box sx={{ pb: 2 }}>
        {grouped.map((section) => {
          const meta = SECTION_META[section.key] || { label: section.key };
          const labelKey = `projects.tabnav.${section.key}`;
          const label = t(labelKey, meta.label);
          return (
            <Box key={section.key}>
              <NavSectionLabel>
                <span>{label}</span>
              </NavSectionLabel>
              {section.items.map((tab) => {
                // `selectionId` is the stable identifier `setActive`
                // receives — the key prop when provided (i18n-safe),
                // else the name. Keeps existing call-sites working.
                const { name, Icon, key } = tab;
                const selectionId = key || name;
                const isActive = active === selectionId;
                return (
                  <NavItem
                    key={selectionId}
                    active={isActive}
                    onClick={() => {
                      setActive(selectionId);
                      setOpenDrawer(false);
                    }}
                  >
                    <Icon className="nav-icon" />
                    <Box component="span">{name}</Box>
                  </NavItem>
                );
              })}
            </Box>
          );
        })}
      </Box>
    );
  }

  // Mobile trigger — show the active tab's label so the user knows
  // where they are. Better than the old generic "Show More".
  const activeTab = tabs.find((tb) => (tb.key || tb.name) === active);
  const activeLabel = activeTab?.name;

  if (downMd) {
    return (
      <Fragment>
        <NavCard sx={{ p: 1.25 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <IconButton
              size="small"
              onClick={() => setOpenDrawer(true)}
              sx={{ color: ACCENT }}
            >
              <MenuIcon />
            </IconButton>
            <Box
              component="span"
              sx={{
                fontFamily: FONT_MONO,
                fontSize: "0.7rem",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                fontWeight: 800,
                color: ACCENT,
                flex: 1,
              }}
            >
              {activeLabel || t("tabnav.menu")}
            </Box>
          </Box>
        </NavCard>

        <Drawer anchor="left" open={openDrawer} onClose={() => setOpenDrawer(false)}>
          <Box sx={{ minWidth: 240, background: "#fff", height: "100%" }}>
            <TabListContent />
          </Box>
        </Drawer>
      </Fragment>
    );
  }

  return (
    <NavCard elevation={0}>
      <TabListContent />
    </NavCard>
  );
}
