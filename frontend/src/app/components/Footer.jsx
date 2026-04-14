import { AppBar, ThemeProvider, Toolbar, styled, useTheme } from "@mui/material";
import React, { useState, useEffect } from "react";

import { Paragraph } from "./Typography";
import useSettings from "app/hooks/useSettings";
import useAuth from "app/hooks/useAuth";
import { topBarHeight } from "app/utils/constant";
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { useNavigate } from "react-router-dom";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import api from "app/utils/api";

const AppFooter = styled(Toolbar)(() => ({
  display: "flex",
  alignItems: "center",
  minHeight: topBarHeight,
  "@media (max-width: 499px)": {
    display: "table",
    width: "100%",
    minHeight: "auto",
    padding: "1rem 0",
    "& .container": {
      flexDirection: "column !important",
      "& a": { margin: "0 0 16px !important" }
    }
  }
}));

const FooterContent = styled("div")(() => ({
  width: "100%",
  display: "flex",
  alignItems: "center",
  padding: "0px 1rem",
  maxWidth: "1170px",
  margin: "0 auto"
}));

export default function Footer() {
  const theme = useTheme();
  const { settings } = useSettings();
  const { platformCapabilities } = usePlatformCapabilities();

  const footerTheme = settings.themes[settings.footer.theme] || theme;

  const [version, setVersion] = useState(null);
  const [updateInfo, setUpdateInfo] = useState(null);
  const auth = useAuth();

  const navigate = useNavigate();
  const isAuthenticated = auth.isAuthenticated;
  const token = auth.user?.token;

  useEffect(() => {
    if (!isAuthenticated) return;

    const opts = { silent: true, credentials: "include" };

    api.get("/version", token, opts)
      .then((d) => { if (d?.version) setVersion(d.version); })
      .catch(() => {});

    api.get("/version/check", token, opts)
      .then((d) => {
        if (d?.current) setVersion(d.current);
        if (d?.update_available) setUpdateInfo(d);
      })
      .catch(() => {});
  }, [isAuthenticated]);

  return (
    <ThemeProvider theme={footerTheme}>
      <ToastContainer
        position="top-right"
        autoClose={8000}
        hideProgressBar={false}
        newestOnTop={false}
        closeOnClick
        rtl={false}
        pauseOnFocusLoss
        draggable
        pauseOnHover
        theme="light"
      />
      <AppBar color="primary" position="static" sx={{ zIndex: 96 }}>
        <AppFooter>
          <FooterContent style={{ textAlign: "center" }}>
            <Paragraph alignItems="center" width={"100%"}>
              {!platformCapabilities.hide_branding && (
                <>
                  Powered by <b><a href="https://github.com/apocas/restai">RESTai</a></b>, so many 'A's and 'I's, so little time...
                  <br />
                </>
              )}
              {(version) && <span style={{ fontSize: "0.7rem" }}>v{version}</span>}
              {updateInfo && (
                <a
                  href={updateInfo.latest_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    marginLeft: 8,
                    fontSize: "0.65rem",
                    fontWeight: 600,
                    padding: "2px 8px",
                    borderRadius: 10,
                    backgroundColor: "rgba(99,102,241,0.15)",
                    color: "#6366f1",
                    textDecoration: "none",
                  }}
                >
                  Update available: v{updateInfo.latest}
                </a>
              )}
            </Paragraph>
          </FooterContent>
        </AppFooter>
      </AppBar>
    </ThemeProvider >
  );
}
