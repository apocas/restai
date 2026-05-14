import { useState, useEffect } from "react";
import { styled, Box, Card, Tooltip, IconButton } from "@mui/material";
import {
  ChevronRight, OpenInNew, Edit as EditIcon,
} from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import { useNavigate, useParams } from "react-router-dom";
import { MatxSidenavContent } from "app/components/MatxSidenav";
import { MatxSidenavContainer } from "app/components/MatxSidenav";
import { topBarHeight } from "app/utils/constant";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";
import ChatContainer from "./components/ChatContainer";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

// Anchor a real pixel height so the chat-panel chain (all `height: 100%`)
// has something to stretch into. Header + footer + the new compact
// trail bar (~44px). Tighter than the old layout because the user
// asked for max chat space.
const CHROME_OFFSET = topBarHeight * 2 + 56;

const Container = styled("div")(({ theme }) => ({
  margin: "16px 32px",
  display: "flex",
  flexDirection: "column",
  height: `calc(100vh - ${CHROME_OFFSET}px)`,
  gap: 12,
  [theme.breakpoints.down("md")]: { margin: "16px 24px" },
  [theme.breakpoints.down("sm")]: {
    margin: 12,
    height: `calc(100vh - ${CHROME_OFFSET + 12}px)`,
  },
}));

// ── Compact trail bar — replaces the old breadcrumb. Navigates back
// to the projects list and the project info page, with a small live
// pulse + project type chip so the context is visible without
// stealing height from the chat below.
const TrailBar = styled(Box, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  position: "relative",
  flex: "0 0 auto",
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "8px 14px",
  borderRadius: 10,
  backgroundColor: "#ffffff",
  border: "1px solid rgba(15,23,42,0.08)",
  overflow: "hidden",
  // Coloured rail down the left edge so the chat surface and the
  // trail read as one piece.
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, top: 0, bottom: 0,
    width: 3,
    background: accent,
    opacity: 0.85,
  },
}));

// ── Outer chat tile — accent rail across the top + hover sweep, same
// vocabulary as the project library / direct-access / cron pages.
// Fills the remaining viewport so the chat panel has all of it.
const ChatTile = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  position: "relative",
  flex: 1,
  minHeight: 0,
  display: "flex",
  flexDirection: "column",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.85,
    pointerEvents: "none",
    zIndex: 2,
  },
  "&::after": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background:
      "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
    animation: `${sweep} 8s ease-in-out infinite`,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1a, 0 4px 10px rgba(15,23,42,0.05)`,
  },
}));

const TrailLink = styled("button")({
  background: "none",
  border: "none",
  padding: 0,
  cursor: "pointer",
  fontFamily: FONT_MONO,
  fontSize: "0.7rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "rgba(15,23,42,0.55)",
  fontWeight: 600,
  transition: "color 0.15s ease",
  "&:hover": {
    color: "#1976d2",
    textDecoration: "underline",
    textUnderlineOffset: "3px",
  },
});

function getAccent(type) {
  return PROJECT_TYPE_COLORS[type]?.color || "#0891b2"; // cyan default — chat is cyan
}

export default function Playground() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState({});
  const auth = useAuth();

  const fetchProject = (projectID) => {
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => {
        setProject(d);
        return d;
      })
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Playground - " + id;
    fetchProject(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const accent = getAccent(project.type);

  return (
    <Container>
      <TrailBar accent={accent}>
        {/* Live pulse — matches the AIHero status dot vocabulary, tells
            the user this surface is "live and connected". */}
        <Box
          sx={{
            width: 8, height: 8,
            borderRadius: "50%",
            background: accent,
            boxShadow: `0 0 8px ${accent}`,
            animation: `${pulse} 2.4s ease-out infinite`,
            flexShrink: 0,
          }}
        />

        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0, flex: 1 }}>
          <TrailLink onClick={() => navigate("/projects")}>Projects</TrailLink>
          <ChevronRight sx={{ fontSize: 14, color: "rgba(15,23,42,0.3)", flexShrink: 0 }} />
          <TrailLink onClick={() => navigate("/project/" + id)}>
            {project.human_name || project.name || id}
          </TrailLink>
          <ChevronRight sx={{ fontSize: 14, color: "rgba(15,23,42,0.3)", flexShrink: 0 }} />
          <Box
            component="span"
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.7rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 700,
              color: accent,
            }}
          >
            Playground
          </Box>
        </Box>

        {/* Right-aligned quick links */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Tooltip title="Open project">
            <IconButton
              size="small"
              onClick={() => navigate("/project/" + id)}
              sx={{
                color: "text.secondary",
                "&:hover": { color: accent, backgroundColor: `${accent}10` },
              }}
            >
              <OpenInNew fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Edit project">
            <IconButton
              size="small"
              onClick={() => navigate("/project/" + id + "/edit")}
              sx={{
                color: "text.secondary",
                "&:hover": { color: accent, backgroundColor: `${accent}10` },
              }}
            >
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </TrailBar>

      <ChatTile accent={accent} elevation={0}>
        <MatxSidenavContainer>
          <MatxSidenavContent>
            <ChatContainer project={project} />
          </MatxSidenavContent>
        </MatxSidenavContainer>
      </ChatTile>
    </Container>
  );
}
