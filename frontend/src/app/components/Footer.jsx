import { useState, useEffect } from "react";
import { Box, styled } from "@mui/material";
import { OpenInNew, GitHub, Bolt } from "@mui/icons-material";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";

import useAuth from "app/hooks/useAuth";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import api from "app/utils/api";
import { FONT_MONO } from "app/components/page/pageStyles";

const ACCENT = "#38bdf8";

// Sky-tinted slate footer that picks up where the sidebar leaves off
// laterally. The sidebar's bottom-right is cyan-tinted; we mirror that
// at the footer's LEFT edge with a horizontal linear gradient that
// fades cyan→slate as you move right, so the sidebar→footer seam reads
// as one continuous panel. A faint cyan bloom at the bottom-right
// closes the rectangle without competing with the seam.
const FooterRoot = styled(Box)(() => ({
  position: "relative",
  width: "100%",
  zIndex: 96,
  backgroundColor: "#0b1220",
  backgroundImage: `
    linear-gradient(90deg, rgba(8,145,178,0.22) 0%, rgba(2,132,199,0.10) 25%, transparent 55%),
    radial-gradient(at 100% 100%, rgba(8,145,178,0.16) 0px, transparent 55%)
  `,
  borderTop: "1px solid rgba(255,255,255,0.06)",
  color: "rgba(255,255,255,0.78)",
  // Sky tick rule along the very top edge.
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0,
    height: 1,
    background: `linear-gradient(90deg, transparent, ${ACCENT}66, transparent)`,
  },
  // Faint grain so the gradient reads as a textured panel.
  "&::after": {
    content: '""',
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
    backgroundImage:
      "radial-gradient(rgba(255,255,255,0.025) 1px, transparent 1px)",
    backgroundSize: "4px 4px",
    mixBlendMode: "overlay",
    opacity: 0.5,
  },
}));

const FooterRow = styled("div")(({ theme }) => ({
  position: "relative",
  zIndex: 1,
  width: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing(2),
  padding: "10px 24px",
  flexWrap: "wrap",
  [theme.breakpoints.down("sm")]: {
    justifyContent: "center",
    padding: "12px 16px",
  },
}));

const Pill = styled("a")(({ tone = "default" }) => {
  const tones = {
    default: { c: "rgba(186,230,253,0.65)", border: "rgba(255,255,255,0.10)", bg: "rgba(255,255,255,0.03)" },
    accent:  { c: ACCENT, border: `${ACCENT}33`, bg: "rgba(56,189,248,0.10)" },
    update:  { c: "#fcd34d", border: "rgba(252,211,77,0.35)", bg: "rgba(252,211,77,0.10)" },
  };
  const t = tones[tone] || tones.default;
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "4px 10px",
    borderRadius: 4,
    fontFamily: FONT_MONO,
    fontSize: "0.66rem",
    fontWeight: 700,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: t.c,
    backgroundColor: t.bg,
    border: `1px solid ${t.border}`,
    textDecoration: "none",
    transition: "all 160ms cubic-bezier(0.4, 0, 0.2, 1)",
    cursor: "pointer",
    "&:hover": {
      color: tone === "update" ? "#fde68a" : ACCENT,
      borderColor: tone === "update" ? "rgba(252,211,77,0.6)" : `${ACCENT}66`,
      backgroundColor: tone === "update" ? "rgba(252,211,77,0.16)" : "rgba(56,189,248,0.16)",
      transform: "translateY(-1px)",
    },
  };
});

const StatusDot = styled("span")(() => ({
  display: "inline-block",
  width: 6,
  height: 6,
  borderRadius: "50%",
  background: ACCENT,
  boxShadow: `0 0 8px ${ACCENT}88`,
}));

export default function Footer() {
  const { platformCapabilities } = usePlatformCapabilities();
  const auth = useAuth();
  const isAuthenticated = auth.isAuthenticated;
  const token = auth.user?.token;

  const [version, setVersion] = useState(null);
  const [updateInfo, setUpdateInfo] = useState(null);

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
  }, [isAuthenticated, token]);

  return (
    <>
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
        theme="dark"
        toastStyle={{
          background: "#0f172a",
          border: "1px solid rgba(56,189,248,0.18)",
          color: "rgba(255,255,255,0.92)",
          fontFamily: FONT_MONO,
          fontSize: "0.82rem",
          borderRadius: 8,
        }}
      />
      <FooterRoot component="footer">
        <FooterRow>
          {/* Left: branding line */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            {!platformCapabilities.hide_branding && (
              <>
                <StatusDot />
                <Box
                  component="span"
                  sx={{
                    fontFamily: FONT_MONO,
                    fontSize: "0.7rem",
                    letterSpacing: "0.06em",
                    color: "rgba(186,230,253,0.7)",
                  }}
                >
                  Powered by{" "}
                  <Box
                    component="a"
                    href="https://github.com/apocas/restai"
                    target="_blank"
                    rel="noopener noreferrer"
                    sx={{
                      fontWeight: 800,
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                      color: ACCENT,
                      textDecoration: "none",
                      "&:hover": { textShadow: `0 0 8px ${ACCENT}88` },
                    }}
                  >
                    RESTai
                  </Box>
                  <Box component="span" sx={{ color: "rgba(186,230,253,0.4)", ml: 0.5 }}>
                    · so many 'A's and 'I's, so little time…
                  </Box>
                </Box>
              </>
            )}
          </Box>

          {/* Right: version + update + source */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            {version && (
              <Pill
                href={`https://github.com/apocas/restai/releases/tag/v${version}`}
                target="_blank"
                rel="noopener noreferrer"
                tone="accent"
              >
                <Box component="span" sx={{ opacity: 0.6 }}>v</Box>
                {version}
              </Pill>
            )}
            {updateInfo && (
              <Pill
                href={updateInfo.latest_url}
                target="_blank"
                rel="noopener noreferrer"
                tone="update"
              >
                <Bolt sx={{ fontSize: 12 }} />
                Update v{updateInfo.latest}
              </Pill>
            )}
            <Pill
              href="https://github.com/apocas/restai"
              target="_blank"
              rel="noopener noreferrer"
            >
              <GitHub sx={{ fontSize: 12 }} />
              Source
              <OpenInNew sx={{ fontSize: 10, opacity: 0.6 }} />
            </Pill>
          </Box>
        </FooterRow>
      </FooterRoot>
    </>
  );
}
