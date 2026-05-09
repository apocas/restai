import { Box, Card, IconButton, Tooltip, Typography, styled } from "@mui/material";
import { useNavigate } from "react-router-dom";
import {
  Leaderboard, EmojiEvents, OpenInNew, TrendingUp,
} from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import { FONT_MONO, sweep } from "app/components/page/pageStyles";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";

const ACCENT = "#0891b2"; // cyan-600 — same as the Projects section accent.
const ACCENT_DARK = "#0e7490";
const ACCENT_SOFT = "rgba(8,145,178,0.10)";

const CURRENCY_SYMBOLS = { USD: "$", EUR: "€" };

// Per-rank colour: medal palette for the podium, then mono-slate.
const rankColor = (n) => {
  if (n === 1) return "#eab308";  // gold
  if (n === 2) return "#94a3b8";  // silver
  if (n === 3) return "#c2410c";  // bronze
  return "#64748b";               // slate
};

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

const TopProjectsTable = ({ projects = [], currency = "USD" }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const sym = CURRENCY_SYMBOLS[currency] || "$";

  // Find the top project's token total — used to draw the bar share.
  const maxTokens = Math.max(
    ...projects.map((p) => (p.input_tokens || 0) + (p.output_tokens || 0)),
    1
  );

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
          <Leaderboard />
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
            {t("dashboard.topProjects") || "Top Projects"}
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.4 }}
          >
            Ranked by total tokens consumed
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
          ▸ no traffic yet
        </Box>
      ) : (
        <Box>
          {projects.map((p, idx) => {
            const rank = idx + 1;
            const inT = p.input_tokens || 0;
            const outT = p.output_tokens || 0;
            const total = inT + outT;
            const share = (total / maxTokens) * 100;
            const rc = rankColor(rank);
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
                {/* Rank medal */}
                <Box
                  sx={{
                    width: 32, height: 32, flexShrink: 0,
                    borderRadius: 1.25,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: `linear-gradient(135deg, ${rc}25, ${rc}12)`,
                    border: `1px solid ${rc}55`,
                    color: rc,
                    fontFamily: FONT_MONO,
                    fontWeight: 800,
                    fontSize: "0.85rem",
                    position: "relative",
                  }}
                >
                  {rank <= 3 ? <EmojiEvents sx={{ fontSize: 16 }} /> : rank}
                </Box>

                {/* Name + LLM + share bar */}
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.4 }}>
                    <Box
                      component="span"
                      sx={{
                        fontWeight: 700,
                        fontSize: "0.88rem",
                        color: "text.primary",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        flex: "0 1 auto",
                        minWidth: 0,
                      }}
                    >
                      {p.name}
                    </Box>
                    <TypePill type={p.type} />
                    {p.llm && (
                      <Box
                        component="span"
                        sx={{
                          fontFamily: FONT_MONO,
                          fontSize: "0.62rem",
                          color: "text.disabled",
                          letterSpacing: "0.04em",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        · {p.llm}
                      </Box>
                    )}
                  </Box>
                  {/* Token share bar */}
                  <Box
                    sx={{
                      height: 4,
                      width: "100%",
                      backgroundColor: "rgba(15,23,42,0.06)",
                      overflow: "hidden",
                    }}
                  >
                    <Box
                      sx={{
                        height: "100%",
                        width: `${Math.max(share, 2)}%`,
                        background: `linear-gradient(90deg, ${rc}88, ${rc})`,
                        transition: "width 0.6s cubic-bezier(0.4,0,0.2,1)",
                      }}
                    />
                  </Box>
                </Box>

                {/* Tokens + cost */}
                <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 0.2, minWidth: 90 }}>
                  <Box
                    component="span"
                    sx={{
                      fontFamily: FONT_MONO,
                      fontSize: "0.85rem",
                      fontWeight: 800,
                      color: rc,
                      letterSpacing: "0.02em",
                    }}
                  >
                    {total >= 1000 ? `${(total / 1000).toFixed(1)}K` : total}
                    <Box component="span" sx={{ fontSize: "0.62rem", color: "text.disabled", ml: 0.4 }}>tok</Box>
                  </Box>
                  <Box
                    component="span"
                    sx={{
                      fontFamily: FONT_MONO,
                      fontSize: "0.72rem",
                      fontWeight: 700,
                      color: "#10b981",
                    }}
                  >
                    {sym}{(p.total_cost || 0).toFixed(3)}
                  </Box>
                </Box>

                <Tooltip title="Open project" arrow>
                  <IconButton
                    size="small"
                    onClick={(e) => { e.stopPropagation(); navigate("/project/" + p.id); }}
                    sx={{
                      color: "text.disabled",
                      "&:hover": { color: ACCENT, backgroundColor: `${ACCENT}10` },
                    }}
                  >
                    <OpenInNew fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            );
          })}
        </Box>
      )}

      {/* Footer mini-stat */}
      {projects.length > 0 && (
        <Box
          sx={{
            px: 2.5, py: 1.25,
            borderTop: "1px solid rgba(15,23,42,0.04)",
            display: "flex",
            alignItems: "center",
            gap: 0.75,
            color: "text.secondary",
            fontFamily: FONT_MONO,
            fontSize: "0.66rem",
            letterSpacing: "0.06em",
          }}
        >
          <TrendingUp sx={{ fontSize: 14, color: ACCENT_DARK }} />
          ▸ leader runs <Box component="span" sx={{ color: ACCENT_DARK, fontWeight: 700 }}>
            {Math.round((projects[0].input_tokens || 0) + (projects[0].output_tokens || 0)).toLocaleString()}
          </Box> tokens · {sym}{(projects[0].total_cost || 0).toFixed(3)}
        </Box>
      )}
    </TileCard>
  );
};

export default TopProjectsTable;
