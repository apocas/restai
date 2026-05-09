import {
  Avatar, Box, Button, Card, IconButton, Tooltip, Typography, styled,
} from "@mui/material";
import {
  SportsEsports, FiberNew, OpenInNew, GroupOutlined,
} from "@mui/icons-material";
import sha256 from "crypto-js/sha256";
import { useNavigate } from "react-router-dom";
import { FONT_MONO, sweep } from "app/components/page/pageStyles";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";

const ACCENT = "#0891b2"; // cyan-600 — matches Projects section accent.
const ACCENT_DARK = "#0e7490";
const ACCENT_SOFT = "rgba(8,145,178,0.10)";

const TileCard = styled(Card)(() => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: ACCENT,
    opacity: 0.85,
    pointerEvents: "none",
    zIndex: 2,
  },
  "&::after": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
  },
  "&:hover": {
    borderColor: `${ACCENT}55`,
    boxShadow: `0 18px 36px ${ACCENT}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

function TypePill({ type }) {
  const meta = PROJECT_TYPE_COLORS[type] || { color: "#64748b", bg: "rgba(100,116,139,0.12)" };
  return (
    <Box
      sx={{
        display: "inline-block",
        px: 0.85, py: 0.3,
        borderRadius: 0.75,
        backgroundColor: meta.bg,
        color: meta.color,
        border: `1px solid ${meta.color}33`,
        fontFamily: FONT_MONO,
        fontSize: "0.66rem",
        fontWeight: 800,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
      }}
    >
      {type}
    </Box>
  );
}

// Deterministic per-project gradient hue (so the same project always
// gets the same avatar across reloads).
const hueFor = (s) => {
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
};

function ProjectAvatar({ name }) {
  const initial = (name || "?").trim().charAt(0).toUpperCase();
  const h = hueFor(name || "?");
  const hueBiased = 180 + (h % 60); // bias to cyan/teal/emerald band
  return (
    <Box
      sx={{
        width: 32, height: 32, flexShrink: 0,
        borderRadius: 1,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontFamily: FONT_MONO,
        fontWeight: 800,
        fontSize: "0.78rem",
        background: `linear-gradient(135deg, hsl(${hueBiased}, 65%, 48%) 0%, hsl(${(hueBiased + 30) % 360}, 65%, 38%) 100%)`,
        boxShadow: `0 3px 8px hsla(${hueBiased}, 65%, 48%, 0.35)`,
        textShadow: "0 1px 2px rgba(0,0,0,0.18)",
      }}
    >
      {initial}
    </Box>
  );
}

export default function ProjectsTable({ projects = [], title = "Projects", compact = false }) {
  const navigate = useNavigate();

  return (
    <TileCard elevation={0}>
      {/* Header */}
      <Box
        sx={{
          px: 2.5, pt: 2, pb: 1.75,
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          borderBottom: "1px solid rgba(15,23,42,0.06)",
          flexWrap: "wrap",
        }}
      >
        <Box
          sx={{
            width: 36, height: 36, flexShrink: 0,
            borderRadius: 1.5,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: `${ACCENT}1a`,
            color: ACCENT,
            "& svg": { fontSize: 20 },
          }}
        >
          <FiberNew />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.72rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 800,
              color: ACCENT,
              lineHeight: 1,
            }}
          >
            {title}
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.4 }}
          >
            Most recently created
          </Typography>
        </Box>
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            px: 1, py: 0.4,
            borderRadius: 0.75,
            backgroundColor: ACCENT_SOFT,
            border: `1px solid ${ACCENT}33`,
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            fontWeight: 700,
            color: ACCENT,
          }}
        >
          {projects.length}
        </Box>
        {!compact && (
          <Button
            size="small"
            variant="contained"
            startIcon={<FiberNew fontSize="small" />}
            onClick={() => navigate("/projects/new")}
            sx={{
              textTransform: "none",
              fontWeight: 700,
              background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
              boxShadow: `0 4px 14px ${ACCENT}55`,
              "&:hover": {
                background: `linear-gradient(135deg, ${ACCENT} 0%, #155e75 100%)`,
                boxShadow: `0 6px 18px ${ACCENT}77`,
              },
            }}
          >
            New project
          </Button>
        )}
      </Box>

      {/* Rows */}
      {projects.length === 0 ? (
        <Box
          sx={{
            py: 4,
            textAlign: "center",
            color: "text.disabled",
            fontFamily: FONT_MONO,
            fontSize: "0.78rem",
            letterSpacing: "0.04em",
          }}
        >
          ▸ no projects yet
        </Box>
      ) : (
        <Box>
          {projects.map((p, idx) => {
            const users = Array.isArray(p.users) ? p.users : [];
            const teamName = p.team?.name || null;
            return (
              <Box
                key={p.id}
                onClick={() => navigate("/project/" + p.id)}
                sx={{
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                  gap: 1.25,
                  px: 2.5, py: 1.5,
                  cursor: "pointer",
                  borderBottom: idx < projects.length - 1 ? "1px solid rgba(15,23,42,0.04)" : "none",
                  transition: "background-color 0.15s ease",
                  "&:hover": { backgroundColor: ACCENT_SOFT },
                }}
              >
                <ProjectAvatar name={p.name} />

                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.25, flexWrap: "wrap" }}>
                    <Box
                      component="span"
                      sx={{
                        fontWeight: 700,
                        fontSize: "0.88rem",
                        color: "text.primary",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        minWidth: 0,
                      }}
                    >
                      {p.name}
                    </Box>
                    <TypePill type={p.type} />
                  </Box>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                    {p.llm && (
                      <Box
                        component="span"
                        sx={{
                          fontFamily: FONT_MONO,
                          fontSize: "0.62rem",
                          color: "text.disabled",
                          letterSpacing: "0.04em",
                        }}
                      >
                        ◆ {p.llm}
                      </Box>
                    )}
                    {teamName && (
                      <Box
                        component="span"
                        sx={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 0.3,
                          fontFamily: FONT_MONO,
                          fontSize: "0.62rem",
                          color: "text.disabled",
                          letterSpacing: "0.04em",
                        }}
                      >
                        <GroupOutlined sx={{ fontSize: 10 }} /> {teamName}
                      </Box>
                    )}
                  </Box>
                </Box>

                {/* User avatars */}
                {users.length > 0 && (
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    {users.slice(0, 3).map((u, i) => (
                      <Tooltip key={u.id || u.username || i} title={u.username || ""} arrow>
                        <Avatar
                          src={`https://www.gravatar.com/avatar/${sha256(u.username || "")}?d=identicon`}
                          sx={{
                            width: 24, height: 24,
                            ml: i === 0 ? 0 : -0.75,
                            border: "2px solid #fff",
                            boxShadow: "0 0 0 1px rgba(15,23,42,0.08)",
                          }}
                        />
                      </Tooltip>
                    ))}
                    {users.length > 3 && (
                      <Tooltip title={users.slice(3).map((u) => u.username).join(", ")} arrow>
                        <Box
                          sx={{
                            ml: -0.75,
                            width: 24, height: 24,
                            borderRadius: "50%",
                            background: "rgba(15,23,42,0.08)",
                            border: "2px solid #fff",
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontFamily: FONT_MONO,
                            fontSize: "0.56rem",
                            fontWeight: 700,
                            color: "text.secondary",
                          }}
                        >
                          +{users.length - 3}
                        </Box>
                      </Tooltip>
                    )}
                  </Box>
                )}

                {/* Action icons */}
                <Box sx={{ display: "flex", gap: 0.25 }}>
                  <Tooltip title="Playground" arrow>
                    <IconButton
                      size="small"
                      onClick={(e) => { e.stopPropagation(); navigate("/project/" + p.id + "/playground"); }}
                      sx={{
                        color: "text.disabled",
                        "&:hover": { color: "#7c3aed", backgroundColor: "rgba(124,58,237,0.08)" },
                      }}
                    >
                      <SportsEsports fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Open project" arrow>
                    <IconButton
                      size="small"
                      onClick={(e) => { e.stopPropagation(); navigate("/project/" + p.id); }}
                      sx={{
                        color: "text.disabled",
                        "&:hover": { color: ACCENT, backgroundColor: ACCENT_SOFT },
                      }}
                    >
                      <OpenInNew fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
    </TileCard>
  );
}
