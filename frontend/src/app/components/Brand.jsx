import { Box, IconButton, Menu, MenuItem, styled, Tooltip } from "@mui/material";

import { Span } from "./Typography";
import { MatxLogo } from "app/components";
import useSettings from "app/hooks/useSettings";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import { useTeamBranding } from "app/contexts/TeamBrandingContext";
import { useState } from "react";
import { SwapHoriz } from "@mui/icons-material";

const BrandRoot = styled(Box)(() => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "20px 18px 20px 29px"
}));

const StyledSpan = styled(Span)(({ mode }) => ({
  fontSize: 18,
  marginLeft: ".5rem",
  display: mode === "compact" ? "none" : "block"
}));

export default function Brand({ children }) {
  const { settings } = useSettings();
  const { platformCapabilities } = usePlatformCapabilities();
  const { branding, brandedTeams, activeTeamId, setActiveTeamId } = useTeamBranding();
  const leftSidebar = settings.layout1Settings.leftSidebar;
  const { mode } = leftSidebar;
  const [anchorEl, setAnchorEl] = useState(null);

  const appName = branding?.app_name || platformCapabilities.app_name || "RESTai";
  const showSwitcher = brandedTeams.length > 1;

  return (
    <BrandRoot>
      <Box display="flex" alignItems="center">
        {branding?.logo_url ? (
          <img width="30px" height="30px" src={branding.logo_url} alt="logo" style={{ objectFit: "contain" }} />
        ) : (
          <MatxLogo />
        )}
        <StyledSpan mode={mode} className="sidenavHoverShow">
          {appName}
        </StyledSpan>
      </Box>

      <Box className="sidenavHoverShow" sx={{ display: mode === "compact" ? "none" : "flex", alignItems: "center", gap: 0.5 }}>
        {showSwitcher && (
          <>
            <Tooltip title="Switch team branding">
              <IconButton size="small" onClick={(e) => setAnchorEl(e.currentTarget)}>
                <SwapHoriz fontSize="small" />
              </IconButton>
            </Tooltip>
            <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
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
        {children || null}
      </Box>
    </BrandRoot>
  );
}
