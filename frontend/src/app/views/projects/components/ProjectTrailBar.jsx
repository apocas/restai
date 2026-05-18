import { styled, Box, IconButton, Tooltip } from "@mui/material";
import { ChevronRight, OpenInNew, Edit as EditIcon, PlayArrow } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { FONT_MONO, pulse } from "app/components/page/pageStyles";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";

// Shared "trail" — the compact replacement for the old breadcrumb that
// also surfaces back-to-project, edit, and playground shortcuts. Lives
// at the top of every project sub-page (Playground / Evals / Guards /
// Logs / API) so navigation back to the project is one click no matter
// which deep view you're on.
//
// Visual vocabulary intentionally identical across pages: live pulse
// in the project's type accent, two monospace breadcrumbs, accent
// label for the current page, and a right-side IconButton cluster.

const Bar = styled(Box, {
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
  marginTop: 16,
  marginBottom: 16,
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, top: 0, bottom: 0,
    width: 3,
    background: accent,
    opacity: 0.85,
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
  return PROJECT_TYPE_COLORS[type]?.color || "#0891b2";
}

export default function ProjectTrailBar({ project, label, showPlayground = true }) {
  const navigate = useNavigate();
  const id = project?.id;
  const accent = getAccent(project?.type);
  const projectLabel = project?.human_name || project?.name || (id ?? "—");

  return (
    <Bar accent={accent}>
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

      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0, flex: 1, flexWrap: "wrap" }}>
        <TrailLink onClick={() => navigate("/projects")}>Projects</TrailLink>
        <ChevronRight sx={{ fontSize: 14, color: "rgba(15,23,42,0.3)", flexShrink: 0 }} />
        <TrailLink onClick={() => id && navigate("/project/" + id)}>
          {projectLabel}
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
          {label}
        </Box>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        {showPlayground && id && (
          <Tooltip title="Open playground">
            <IconButton
              size="small"
              onClick={() => navigate("/project/" + id + "/playground")}
              sx={{
                color: "text.secondary",
                "&:hover": { color: accent, backgroundColor: `${accent}10` },
              }}
            >
              <PlayArrow fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Open project">
          <IconButton
            size="small"
            onClick={() => id && navigate("/project/" + id)}
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
            onClick={() => id && navigate("/project/" + id + "/edit")}
            sx={{
              color: "text.secondary",
              "&:hover": { color: accent, backgroundColor: `${accent}10` },
            }}
          >
            <EditIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
    </Bar>
  );
}
