import { useState, useMemo } from "react";
import {
  Box, Button, Card, Grid, IconButton, Tooltip, Typography, styled,
} from "@mui/material";
import {
  Edit, Delete, Hub, Storage, Public, Lock, ContentCopy, OpenInNew,
  Code, GridView, AltRoute, Workspaces, QrCode2,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import QRCode from "react-qr-code";
import ReactJson from "@microlink/react-json-view";
import useAuth from "app/hooks/useAuth";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

// Embeddings = vector space / encoder / dimensions → teal-600 reads as
// "semantic geometry". Matches the per-section colour used for
// embeddings inside TeamView so the trio is consistent.
const ACCENT = "#0d9488";        // teal-600
const ACCENT_DARK = "#0f766e";   // teal-700
const ACCENT_SOFT = "rgba(13,148,136,0.10)";

const TileCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
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
    background: accent,
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
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

function TileHeader({ icon, title, subtitle, accent = ACCENT, action }) {
  return (
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
          background: `${accent}1a`,
          color: accent,
          "& svg": { fontSize: 20 },
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: accent,
            lineHeight: 1,
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.4 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {action}
    </Box>
  );
}

const StatCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  padding: 16,
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.85,
    zIndex: 2,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
}));

function StatTile({ icon, label, value, accent = ACCENT, sub }) {
  return (
    <StatCard accent={accent} elevation={0}>
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.25 }}>
        <Box
          sx={{
            width: 38, height: 38, flexShrink: 0,
            borderRadius: 1.5,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: `linear-gradient(135deg, ${accent}25, ${accent}12)`,
            border: `1px solid ${accent}33`,
            color: accent,
            "& svg": { fontSize: 20 },
          }}
        >
          {icon}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "0.6rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 700,
              color: "text.secondary",
              lineHeight: 1,
            }}
          >
            {label}
          </Box>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "1.4rem",
              fontWeight: 800,
              color: accent,
              lineHeight: 1.1,
              mt: 0.4,
              wordBreak: "break-word",
            }}
          >
            {value}
          </Box>
          {sub && (
            <Box
              component="span"
              sx={{
                display: "block",
                fontFamily: FONT_MONO,
                fontSize: "0.62rem",
                color: "text.disabled",
                mt: 0.3,
              }}
            >
              {sub}
            </Box>
          )}
        </Box>
      </Box>
    </StatCard>
  );
}

// Key/value row — left column is the field key in mono uppercase, right
// is the value rendered with appropriate context.
function AttrRow({ icon: Icon, label, children, accent = ACCENT, last = false }) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 2,
        px: 2.5, py: 1.5,
        borderBottom: last ? "none" : "1px solid rgba(15,23,42,0.06)",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.75,
          minWidth: 160,
          flexShrink: 0,
        }}
      >
        {Icon && (
          <Icon sx={{ fontSize: 14, color: accent, opacity: 0.7 }} />
        )}
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.66rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            fontWeight: 700,
            color: "text.secondary",
          }}
        >
          {label}
        </Box>
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>{children}</Box>
    </Box>
  );
}

function MonoPill({ value, color = ACCENT, icon: Icon }) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 0.85, py: 0.35,
        borderRadius: 0.75,
        backgroundColor: `${color}10`,
        border: `1px solid ${color}33`,
      }}
    >
      {Icon && <Icon sx={{ fontSize: 12, color }} />}
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.74rem",
          fontWeight: 700,
          letterSpacing: "0.04em",
          color,
        }}
      >
        {value}
      </Box>
    </Box>
  );
}

export default function EmbeddingInfo({ embedding, projects, usedBy = 0 }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const auth = useAuth();
  const [showQR, setShowQR] = useState(false);

  const handleDelete = () => {
    if (!window.confirm(t("embeddings.info.confirmDelete", { name: embedding.name }))) return;
    api.delete("/embeddings/" + embedding.id, auth.user.token)
      .then(() => navigate("/embeddings"))
      .catch(() => {});
  };

  const copyName = () => {
    navigator.clipboard.writeText(embedding.name).then(() => {
      toast.success(t("common.copied") || "Copied");
    });
  };

  // Best-effort options parse — tolerate non-JSON strings without
  // crashing the page.
  const optionsObj = useMemo(() => {
    if (!embedding.options) return null;
    try { return JSON.parse(embedding.options); } catch { return null; }
  }, [embedding.options]);

  const optionsCount = optionsObj ? Object.keys(optionsObj).length : 0;
  const isPublic = (embedding.privacy || "").toLowerCase() === "public";
  const projectsUsing = (projects || []).filter((p) => p.embeddings === embedding.name);

  return (
    <Box>
      <Grid container spacing={2} sx={{ mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Code />}
            label="Class"
            value={embedding.class_name || "—"}
            accent={ACCENT}
            sub="LlamaIndex provider"
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<GridView />}
            label="Dimension"
            value={embedding.dimension ? `${embedding.dimension}` : "—"}
            accent="#0891b2"
            sub={embedding.dimension ? "vectors per token" : "auto-detected"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={isPublic ? <Public /> : <Lock />}
            label="Privacy"
            value={(embedding.privacy || "—").toUpperCase()}
            accent={isPublic ? "#10b981" : "#f59e0b"}
            sub={isPublic ? "any team can attach" : "manually shared"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Workspaces />}
            label="Used by"
            value={usedBy}
            accent="#7c3aed"
            sub={usedBy === 1 ? "project" : "projects"}
          />
        </Grid>
      </Grid>

      <Grid container spacing={2.5}>
        {/* Identity / actions */}
        <Grid item xs={12} md={4}>
          <TileCard elevation={0} accent={ACCENT}>
            <Box sx={{ p: 3, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
              <Box
                sx={{
                  width: 88, height: 88,
                  borderRadius: "50%",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: `radial-gradient(circle at 30% 30%, ${ACCENT}33, ${ACCENT}11 60%, transparent 70%)`,
                  position: "relative",
                  mb: 1.5,
                  "&::before": {
                    content: '""',
                    position: "absolute",
                    inset: -6,
                    borderRadius: "50%",
                    border: `1px dashed ${ACCENT}55`,
                    animation: `${pulse} 4s ease-in-out infinite`,
                  },
                }}
              >
                <Hub sx={{ fontSize: 40, color: ACCENT }} />
              </Box>
              <Box
                component="span"
                sx={{
                  display: "block",
                  fontFamily: FONT_MONO,
                  fontSize: "1.1rem",
                  fontWeight: 800,
                  color: "text.primary",
                  letterSpacing: "0.02em",
                  mb: 0.5,
                  wordBreak: "break-word",
                }}
              >
                {embedding.name}
              </Box>
              <Box
                component="span"
                sx={{
                  display: "block",
                  fontFamily: FONT_MONO,
                  fontSize: "0.66rem",
                  color: "text.disabled",
                  letterSpacing: "0.06em",
                  mb: 1.5,
                }}
              >
                EMBEDDING/{String(embedding.id || 0).padStart(4, "0")}
              </Box>
              <Box sx={{ display: "flex", gap: 1, justifyContent: "center", flexWrap: "wrap" }}>
                <Tooltip title={t("common.copy") || "Copy name"} arrow>
                  <IconButton
                    size="small"
                    onClick={copyName}
                    sx={{ color: ACCENT, "&:hover": { backgroundColor: ACCENT_SOFT } }}
                  >
                    <ContentCopy fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={showQR ? "Hide QR" : "Share via QR"} arrow>
                  <IconButton
                    size="small"
                    onClick={() => setShowQR((v) => !v)}
                    sx={{ color: ACCENT, "&:hover": { backgroundColor: ACCENT_SOFT } }}
                  >
                    <QrCode2 fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
              {showQR && (
                <Box
                  sx={{
                    mt: 2,
                    p: 1.5,
                    borderRadius: 1.5,
                    background: "#fff",
                    border: `1px solid ${ACCENT}33`,
                    display: "inline-block",
                  }}
                >
                  <QRCode
                    size={120}
                    style={{ width: 120, height: 120 }}
                    value={window.location.href || "RESTai"}
                    viewBox="0 0 256 256"
                  />
                </Box>
              )}
            </Box>

            {auth.user.is_admin && (
              <Box
                sx={{
                  px: 2, py: 1.5,
                  borderTop: "1px solid rgba(15,23,42,0.06)",
                  display: "flex",
                  gap: 1,
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                }}
              >
                <Button
                  variant="contained"
                  startIcon={<Edit fontSize="small" />}
                  onClick={() => navigate("/embedding/" + embedding.id + "/edit")}
                  sx={{
                    textTransform: "none",
                    fontWeight: 700,
                    background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
                    boxShadow: `0 4px 14px ${ACCENT}55`,
                    "&:hover": {
                      background: `linear-gradient(135deg, ${ACCENT} 0%, #134e4a 100%)`,
                      boxShadow: `0 6px 18px ${ACCENT}77`,
                    },
                  }}
                >
                  {t("common.edit")}
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Delete fontSize="small" />}
                  onClick={handleDelete}
                  sx={{
                    textTransform: "none",
                    color: "#ef4444",
                    borderColor: "rgba(239,68,68,0.4)",
                    "&:hover": { borderColor: "#ef4444", backgroundColor: "rgba(239,68,68,0.06)" },
                  }}
                >
                  {t("common.delete")}
                </Button>
              </Box>
            )}
          </TileCard>
        </Grid>

        {/* Attributes + Options + Projects */}
        <Grid item xs={12} md={8}>
          <TileCard elevation={0} accent={ACCENT}>
            <TileHeader
              icon={<AltRoute />}
              title={t("embeddings.info.title") || "Configuration"}
              subtitle="Provider, privacy, vector geometry"
              accent={ACCENT}
            />
            <Box>
              <AttrRow icon={Code} label={t("embeddings.info.class")} accent={ACCENT}>
                <MonoPill value={embedding.class_name || "—"} color={ACCENT} icon={Code} />
              </AttrRow>
              <AttrRow icon={isPublic ? Public : Lock} label={t("embeddings.info.privacy")} accent={ACCENT}>
                <MonoPill
                  value={(embedding.privacy || "—").toUpperCase()}
                  color={isPublic ? "#10b981" : "#f59e0b"}
                  icon={isPublic ? Public : Lock}
                />
              </AttrRow>
              <AttrRow icon={GridView} label={t("embeddings.info.dimension")} accent={ACCENT}>
                {embedding.dimension ? (
                  <MonoPill value={`${embedding.dimension}-d`} color="#0891b2" icon={GridView} />
                ) : (
                  <Box component="span" sx={{ color: "text.disabled", fontStyle: "italic", fontSize: "0.85rem" }}>—</Box>
                )}
              </AttrRow>
              <AttrRow label={t("embeddings.info.description")} accent={ACCENT} last={!optionsObj && projectsUsing.length === 0}>
                {embedding.description ? (
                  <Typography variant="body2" sx={{ color: "text.primary", whiteSpace: "pre-wrap" }}>
                    {embedding.description}
                  </Typography>
                ) : (
                  <Box component="span" sx={{ color: "text.disabled", fontStyle: "italic", fontSize: "0.85rem" }}>—</Box>
                )}
              </AttrRow>
            </Box>
          </TileCard>

          {/* Options as terminal-style code block */}
          {optionsObj && (
            <Box sx={{ mt: 2.5 }}>
              <TileCard elevation={0} accent={ACCENT}>
                <TileHeader
                  icon={<Storage />}
                  title={t("embeddings.info.options")}
                  subtitle={`${optionsCount} key${optionsCount === 1 ? "" : "s"}`}
                  accent={ACCENT}
                />
                <Box sx={{ p: 2 }}>
                  <Box
                    sx={{
                      borderRadius: 1.5,
                      backgroundColor: "#0b1220",
                      border: "1px solid rgba(255,255,255,0.06)",
                      p: 1.5,
                      position: "relative",
                      overflow: "auto",
                      "& .react-json-view": {
                        backgroundColor: "transparent !important",
                        fontFamily: FONT_MONO,
                        fontSize: "0.78rem",
                      },
                      "&::before": {
                        content: '""',
                        position: "absolute",
                        top: 8, left: 10,
                        width: 10, height: 10,
                        borderRadius: "50%",
                        background: "#fb7185",
                        boxShadow: "16px 0 #fbbf24, 32px 0 #34d399",
                      },
                    }}
                  >
                    <Box sx={{ pl: 6, pt: 0.5 }}>
                      <ReactJson
                        src={optionsObj}
                        enableClipboard
                        name={false}
                        theme="ocean"
                        style={{ backgroundColor: "transparent" }}
                        displayDataTypes={false}
                        collapsed={1}
                      />
                    </Box>
                  </Box>
                </Box>
              </TileCard>
            </Box>
          )}

          {/* Projects using this embedding */}
          {projectsUsing.length > 0 && (
            <Box sx={{ mt: 2.5 }}>
              <TileCard elevation={0} accent="#7c3aed">
                <TileHeader
                  icon={<Workspaces />}
                  title={t("embeddings.info.usedBy") || "Projects using this embedding"}
                  subtitle={`${projectsUsing.length} attached`}
                  accent="#7c3aed"
                />
                <Box sx={{ p: 1.25, display: "flex", flexWrap: "wrap", gap: 1 }}>
                  {projectsUsing.map((p) => (
                    <Box
                      key={p.id}
                      onClick={() => navigate(`/project/${p.id}`)}
                      sx={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 0.75,
                        px: 1.25, py: 0.75,
                        borderRadius: 1,
                        cursor: "pointer",
                        backgroundColor: "rgba(124,58,237,0.06)",
                        border: "1px solid rgba(124,58,237,0.25)",
                        transition: "all 0.15s ease",
                        "&:hover": {
                          backgroundColor: "rgba(124,58,237,0.12)",
                          borderColor: "#7c3aed",
                          transform: "translateY(-1px)",
                        },
                      }}
                    >
                      <Box
                        component="span"
                        sx={{
                          fontWeight: 600,
                          fontSize: "0.84rem",
                          color: "#5b21b6",
                        }}
                      >
                        {p.name}
                      </Box>
                      <OpenInNew sx={{ fontSize: 12, color: "#7c3aed", opacity: 0.7 }} />
                    </Box>
                  ))}
                </Box>
              </TileCard>
            </Box>
          )}
        </Grid>
      </Grid>
    </Box>
  );
}
