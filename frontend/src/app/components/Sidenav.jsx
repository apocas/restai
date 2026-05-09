import { Fragment } from "react";
import { styled } from "@mui/material/styles";
import Scrollbar from "react-perfect-scrollbar";

import { MatxVerticalNav } from "app/components";
import useSettings from "app/hooks/useSettings";
import { useNavigations } from "app/navigations";
import useAuth from "app/hooks/useAuth";
import { navGuard } from "app/auth/navGuard";

const StyledScrollBar = styled(Scrollbar)(() => ({
  paddingLeft: "0.4rem",
  paddingRight: "0.4rem",
  position: "relative",
  // Custom scrollbar — sky-tinted instead of grey.
  "& .ps__rail-y": { width: 6 },
  "& .ps__thumb-y": {
    width: 4,
    background: "rgba(56,189,248,0.35)",
    "&:hover, &:focus": { background: "rgba(56,189,248,0.55)" },
  },
}));

const SideNavMobile = styled("div")(({ theme }) => ({
  position: "fixed",
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  zIndex: -1,
  width: "100vw",
  background: "rgba(0, 0, 0, 0.54)",
  [theme.breakpoints.up("lg")]: { display: "none" }
}));

export default function Sidenav({ children }) {
  const { settings, updateSettings } = useSettings();
  const { user } = useAuth();
  const navigationItems = useNavigations();
  const navItems = navGuard(navigationItems, user);

  const updateSidebarMode = (sidebarSettings) => {
    let activeLayoutSettingsName = settings.activeLayout + "Settings";
    let activeLayoutSettings = settings[activeLayoutSettingsName];

    updateSettings({
      ...settings,
      [activeLayoutSettingsName]: {
        ...activeLayoutSettings,
        leftSidebar: {
          ...activeLayoutSettings.leftSidebar,
          ...sidebarSettings
        }
      }
    });
  };

  return (
    <Fragment>
      <StyledScrollBar options={{ suppressScrollX: true }}>
        {children}
        <MatxVerticalNav items={navItems} />
      </StyledScrollBar>

      <SideNavMobile onClick={() => updateSidebarMode({ mode: "close" })} />
    </Fragment>
  );
}
