import { AppBar, ThemeProvider, Toolbar, styled, useTheme } from "@mui/material";
import React, { useState, useEffect } from "react";

import { Paragraph } from "./Typography";
import useSettings from "app/hooks/useSettings";
import { topBarHeight } from "app/utils/constant";
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { useNavigate } from "react-router-dom";

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

  const footerTheme = settings.themes[settings.footer.theme] || theme;

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [version, setVersion] = useState([]);

  const navigate = useNavigate();

  const fetchVersion = () => {
    return fetch(url + "/version")
      .then((res) => res.json())
      .then((d) => {
        setVersion(d.version)
      }).catch(err => {
        console.log(err.toString());
      });
  }

  useEffect(() => {
    fetchVersion();
  }, []);

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
              {!process.env.REACT_APP_RESTAI_HIDE && (
                <>
                  Powered by <b><a href="https://github.com/apocas/restai">RESTai</a></b>, so many 'A's and 'I's, so little time...
                  <br />
                </>
              )}
              {(version) && <span style={{ fontSize: "0.7rem" }}>Core v{version + ', UI v' + process.env.REACT_APP_VERSION}</span>}
            </Paragraph>
          </FooterContent>
        </AppFooter>
      </AppBar>
    </ThemeProvider >
  );
}
