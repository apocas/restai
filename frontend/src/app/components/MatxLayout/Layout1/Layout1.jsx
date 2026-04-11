import { useEffect, useRef, memo } from "react";
import { ThemeProvider, useMediaQuery, Box, Button, styled, useTheme } from "@mui/material";
import Scrollbar from "react-perfect-scrollbar";
import { Outlet } from "react-router-dom";

import useSettings from "app/hooks/useSettings";
import useAuth from "app/hooks/useAuth";

import Layout1Topbar from "./Layout1Topbar";
import Layout1Sidenav from "./Layout1Sidenav";

import Footer from "app/components/Footer";
import QuickActionFab from "app/components/QuickActionFab";
import { MatxSuspense } from "app/components";
import SidenavTheme from "app/components/MatxTheme/SidenavTheme/SidenavTheme";

import { sidenavCompactWidth, sideNavWidth } from "app/utils/constant";

const Layout1Root = styled(Box)(({ theme }) => ({
  display: "flex",
  background: theme.palette.background.default
}));

const ContentBox = styled(Box)(() => ({
  height: "100%",
  display: "flex",
  overflowY: "auto",
  overflowX: "hidden",
  flexDirection: "column",
  justifyContent: "space-between"
}));

const StyledScrollBar = styled(Scrollbar)(() => ({
  height: "100%",
  position: "relative",
  display: "flex",
  flexGrow: "1",
  flexDirection: "column"
}));

const LayoutContainer = styled(Box)(({ width, open }) => ({
  height: "100vh",
  display: "flex",
  flexGrow: "1",
  flexDirection: "column",
  verticalAlign: "top",
  marginLeft: width,
  position: "relative",
  overflow: "hidden",
  transition: "all 0.3s ease",
  marginRight: open ? 50 : 0
}));

const ImpersonationBanner = styled(Box)({
  backgroundColor: "#ff9800",
  color: "#fff",
  padding: "6px 16px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  fontSize: "0.875rem",
  fontWeight: 500,
  zIndex: 9999,
});

const RestrictedBanner = styled(Box)({
  backgroundColor: "#ef4444",
  color: "#fff",
  padding: "6px 16px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  fontSize: "0.875rem",
  fontWeight: 500,
  zIndex: 9999,
});

const Layout1 = () => {
  const { settings, updateSettings } = useSettings();
  const { user, isImpersonating, exitImpersonation } = useAuth();
  const { layout1Settings } = settings;
  const topbarTheme = settings.themes[layout1Settings.topbar.theme];
  const {
    leftSidebar: { mode: sidenavMode, show: showSidenav }
  } = layout1Settings;

  const getSidenavWidth = () => {
    switch (sidenavMode) {
      case "full":
        return sideNavWidth;

      case "compact":
        return sidenavCompactWidth;

      default:
        return "0px";
    }
  };

  const sidenavWidth = getSidenavWidth();
  const theme = useTheme();
  const isMdScreen = useMediaQuery(theme.breakpoints.down("md"));

  const ref = useRef({ isMdScreen, settings });
  const layoutClasses = `theme-${theme.palette.type}`;

  useEffect(() => {
    let { settings } = ref.current;
    let sidebarMode = settings.layout1Settings.leftSidebar.mode;
    if (settings.layout1Settings.leftSidebar.show) {
      let mode = isMdScreen ? "close" : sidebarMode;
      updateSettings({ layout1Settings: { leftSidebar: { mode } } });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMdScreen]);

  return (
    <Layout1Root className={layoutClasses}>
      {showSidenav && sidenavMode !== "close" && (
        <SidenavTheme>
          <Layout1Sidenav />
        </SidenavTheme>
      )}

      <LayoutContainer width={sidenavWidth} >
        {isImpersonating && (
          <ImpersonationBanner>
            Impersonating: {user?.username}
            <Button
              size="small"
              variant="contained"
              color="inherit"
              sx={{ ml: 1, color: "#ff9800", backgroundColor: "#fff", fontWeight: "bold", "&:hover": { backgroundColor: "#f5f5f5" } }}
              onClick={exitImpersonation}
            >
              Exit
            </Button>
          </ImpersonationBanner>
        )}
        {user?.is_restricted && (
          <RestrictedBanner>
            Restricted mode — You can only view and chat with existing projects
          </RestrictedBanner>
        )}
        {layout1Settings.topbar.show && layout1Settings.topbar.fixed && (
          <ThemeProvider theme={topbarTheme}>
            <Layout1Topbar fixed={true} className="elevation-z8" />
          </ThemeProvider>
        )}

        {settings.perfectScrollbar && (
          <StyledScrollBar>
            {layout1Settings.topbar.show && !layout1Settings.topbar.fixed && (
              <ThemeProvider theme={topbarTheme}>
                <Layout1Topbar />
              </ThemeProvider>
            )}
            <Box flexGrow={1} position="relative">
              <MatxSuspense>
                <Outlet />
              </MatxSuspense>
            </Box>

            {settings.footer.show && !settings.footer.fixed && <Footer />}
          </StyledScrollBar>
        )}

        {!settings.perfectScrollbar && (
          <ContentBox>
            {layout1Settings.topbar.show && !layout1Settings.topbar.fixed && (
              <ThemeProvider theme={topbarTheme}>
                <Layout1Topbar />
              </ThemeProvider>
            )}

            <Box flexGrow={1} position="relative">
              <MatxSuspense>
                <Outlet />
              </MatxSuspense>
            </Box>

            {settings.footer.show && !settings.footer.fixed && <Footer />}
          </ContentBox>
        )}

        {settings.footer.show && settings.footer.fixed && <Footer />}
      </LayoutContainer>

      <QuickActionFab />
    </Layout1Root>
  );
};

export default memo(Layout1);
