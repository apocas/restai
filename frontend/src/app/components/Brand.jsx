import { useState } from "react";
import {
  Box, IconButton, Menu, MenuItem, styled, Tooltip,
} from "@mui/material";
import { SwapHoriz, MenuOpen } from "@mui/icons-material";

import { Span } from "./Typography";
import { MatxLogo } from "app/components";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import { useTeamBranding } from "app/contexts/TeamBrandingContext";

const ACCENT = "#38bdf8";

const BrandRoot = styled(Box)(() => ({
  position: "relative",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "22px 18px 18px 22px",
  borderBottom: "1px solid rgba(255,255,255,0.06)",
  // Faint sky glow under the brand mark.
  "&::after": {
    content: '""',
    position: "absolute",
    left: 22, right: 22, bottom: 0,
    height: 1,
    background: `linear-gradient(90deg, transparent, ${ACCENT}55, transparent)`,
  },
}));

const BrandName = styled(Span)(() => ({
  fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
  fontSize: "0.95rem",
  fontWeight: 800,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  marginLeft: 12,
  color: "#ffffff",
  whiteSpace: "nowrap",
}));

const LogoBadge = styled(Box)(() => ({
  width: 32,
  height: 32,
  borderRadius: 8,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  background: `linear-gradient(135deg, ${ACCENT}33, ${ACCENT}11)`,
  border: `1px solid ${ACCENT}44`,
  flexShrink: 0,
  cursor: "pointer",
  transition: "box-shadow 200ms ease-out, transform 200ms ease-out",
  "&:hover": {
    boxShadow: `0 0 16px ${ACCENT}66`,
    transform: "scale(1.05)",
  },
}));

export default function Brand({ onToggleSidenav }) {
  const { platformCapabilities } = usePlatformCapabilities();
  const { branding, brandedTeams, activeTeamId, setActiveTeamId } = useTeamBranding();
  const [anchorEl, setAnchorEl] = useState(null);

  const appName = branding?.app_name || platformCapabilities.app_name || "RESTai";
  const showSwitcher = brandedTeams.length > 1;

  // Brand always renders its full structure — the sidebar root's CSS
  // hides the name + actions in compact-non-hover mode via .brand-name
  // and .brand-actions. The LogoBadge is always clickable so the user
  // has a one-click toggle even when the chrome is hidden.
  return (
    <BrandRoot className="brand-root">
      <Box display="flex" alignItems="center" sx={{ minWidth: 0 }}>
        <Tooltip title="Toggle sidebar" placement="right" arrow>
          <LogoBadge onClick={onToggleSidenav}>
            {branding?.logo_url ? (
              <img
                width="22"
                height="22"
                src={branding.logo_url}
                alt="logo"
                style={{ objectFit: "contain" }}
              />
            ) : (
              <MatxLogo />
            )}
          </LogoBadge>
        </Tooltip>
        <BrandName className="brand-name">{appName}</BrandName>
      </Box>

      <Box className="brand-actions" sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        {showSwitcher && (
          <>
            <Tooltip title="Switch team branding" arrow>
              <IconButton
                size="small"
                onClick={(e) => setAnchorEl(e.currentTarget)}
                sx={{
                  color: "rgba(186,230,253,0.7)",
                  "&:hover": {
                    color: ACCENT,
                    backgroundColor: "rgba(56,189,248,0.10)",
                  },
                }}
              >
                <SwapHoriz fontSize="small" />
              </IconButton>
            </Tooltip>
            <Menu
              anchorEl={anchorEl}
              open={Boolean(anchorEl)}
              onClose={() => setAnchorEl(null)}
              PaperProps={{
                sx: {
                  background: "#0f172a",
                  border: "1px solid rgba(56,189,248,0.18)",
                  borderRadius: 1.5,
                  mt: 1,
                  "& .MuiMenuItem-root": {
                    fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
                    fontSize: "0.78rem",
                    color: "rgba(255,255,255,0.85)",
                    "&:hover": { background: "rgba(56,189,248,0.10)" },
                    "&.Mui-selected": {
                      background: "rgba(56,189,248,0.14)",
                      color: ACCENT,
                      "&:hover": { background: "rgba(56,189,248,0.18)" },
                    },
                  },
                },
              }}
            >
              {brandedTeams.map((t) => (
                <MenuItem
                  key={t.id}
                  selected={t.id === activeTeamId}
                  onClick={() => { setActiveTeamId(t.id); setAnchorEl(null); }}
                >
                  {t.branding?.app_name || t.name}
                </MenuItem>
              ))}
            </Menu>
          </>
        )}
        <Tooltip title="Collapse sidebar" arrow>
          <IconButton
            size="small"
            onClick={onToggleSidenav}
            sx={{
              color: "rgba(186,230,253,0.7)",
              "&:hover": {
                color: ACCENT,
                backgroundColor: "rgba(56,189,248,0.10)",
              },
            }}
          >
            <MenuOpen fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
    </BrandRoot>
  );
}
