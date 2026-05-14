import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, Grid, IconButton, Tooltip, styled,
} from "@mui/material";
import {
  Add, Edit, Delete, Visibility, Hub, Public, Lock,
  GridView, Code, Storage,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import { useTranslation } from "react-i18next";
import DataList from "app/components/DataList";
import api from "app/utils/api";
import { FONT_MONO, sweep } from "app/components/page/pageStyles";

// Same teal-600 as the Embedding info / edit pages.
const ACCENT = "#0d9488";        // teal-600
const ACCENT_DARK = "#0f766e";   // teal-700
const ACCENT_SOFT = "rgba(13,148,136,0.10)";

// Per-provider colour palette — first match wins. Common LlamaIndex
// providers each get a distinct hue so the catalogue is scannable.
const PROVIDER_COLORS = [
  { match: /openai/i,        color: "#0891b2", short: "OpenAI" },
  { match: /azureopenai/i,   color: "#1d4ed8", short: "Azure" },
  { match: /huggingface/i,   color: "#eab308", short: "HF" },
  { match: /ollama/i,        color: "#7c3aed", short: "Ollama" },
  { match: /gemini|google/i, color: "#dc2626", short: "Gemini" },
  { match: /cohere/i,        color: "#ec4899", short: "Cohere" },
  { match: /voyage/i,        color: "#f97316", short: "Voyage" },
  { match: /fastembed/i,     color: "#10b981", short: "FastEmbed" },
];

const providerMeta = (className) => {
  if (!className) return { color: "#64748b", short: "—" };
  const m = PROVIDER_COLORS.find((p) => p.match.test(className));
  return m || { color: "#64748b", short: className };
};

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

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

// Per-provider segmented bar — one row, segments proportional to count,
// each tinted in the provider's colour with its short label inline.
function ProviderDistribution({ providers, total }) {
  if (!providers.length || !total) return null;
  return (
    <Box>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 0.75,
        }}
      >
        <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
          <Box sx={{ width: 12, height: 2, background: ACCENT }} />
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
            Provider distribution
          </Box>
        </Box>
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            color: "text.disabled",
          }}
        >
          {total} model{total === 1 ? "" : "s"}
        </Box>
      </Box>
      <Box
        sx={{
          display: "flex",
          height: 24,
          overflow: "hidden",
          border: "1px solid rgba(15,23,42,0.10)",
        }}
      >
        {providers.map((p) => {
          const pct = (p.count / total) * 100;
          return (
            <Tooltip key={p.short} title={`${p.short} · ${p.count} (${pct.toFixed(0)}%)`} arrow>
              <Box
                sx={{
                  width: `${pct}%`,
                  background: p.color,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  borderRight: "1px solid rgba(255,255,255,0.35)",
                  cursor: "default",
                  transition: "filter 0.15s ease",
                  "&:hover": { filter: "brightness(1.1)" },
                  "&:last-of-type": { borderRight: "none" },
                }}
              >
                {pct >= 8 && (
                  <Box
                    component="span"
                    sx={{
                      fontFamily: FONT_MONO,
                      fontSize: "0.62rem",
                      fontWeight: 800,
                      letterSpacing: "0.04em",
                      color: "#fff",
                      textShadow: "0 1px 2px rgba(0,0,0,0.25)",
                      whiteSpace: "nowrap",
                      px: 0.5,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {p.short}
                  </Box>
                )}
              </Box>
            </Tooltip>
          );
        })}
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.25, mt: 0.75 }}>
        {providers.map((p) => (
          <Box
            key={p.short}
            sx={{
              display: "inline-flex",
              alignItems: "center",
              gap: 0.5,
              fontFamily: FONT_MONO,
              fontSize: "0.66rem",
              color: "text.secondary",
            }}
          >
            <Box sx={{ width: 8, height: 8, background: p.color }} />
            {p.short} <Box component="span" sx={{ color: "text.disabled" }}>· {p.count}</Box>
          </Box>
        ))}
      </Box>
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
          fontSize: "0.72rem",
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

export default function Embeddings() {
  const { t } = useTranslation();
  const [embeddings, setEmbeddings] = useState([]);
  const auth = useAuth();
  const navigate = useNavigate();
  const isAdmin = auth.user?.is_admin;

  const fetchEmbeddings = () => {
    api.get("/embeddings", auth.user.token)
      .then((d) => setEmbeddings(Array.isArray(d) ? d : (d?.embeddings || [])))
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Embeddings";
    fetchEmbeddings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = (e, em) => {
    e.stopPropagation();
    if (!window.confirm(t("embeddings.info.deleteConfirm", { name: em.name }))) return;
    api.delete("/embeddings/" + em.id, auth.user.token)
      .then(() => {
        toast.success(t("embeddings.info.deleted", { name: em.name }));
        fetchEmbeddings();
      })
      .catch(() => {});
  };

  // Aggregates for stat strip + provider distribution.
  const aggregates = useMemo(() => {
    const total = embeddings.length;
    const publicCount = embeddings.filter((e) => (e.privacy || "").toLowerCase() === "public").length;
    const privateCount = total - publicCount;
    const providerMap = new Map();
    embeddings.forEach((e) => {
      const m = providerMeta(e.class_name);
      const key = m.short;
      if (!providerMap.has(key)) providerMap.set(key, { short: key, color: m.color, count: 0 });
      providerMap.get(key).count++;
    });
    const providers = [...providerMap.values()].sort((a, b) => b.count - a.count);
    const dimSet = new Set(embeddings.map((e) => e.dimension).filter(Boolean));
    return { total, publicCount, privateCount, providers, dimSet };
  }, [embeddings]);

  const columns = [
    {
      key: "name",
      label: t("embeddings.columns.name"),
      sortable: true,
      render: (row) => {
        const meta = providerMeta(row.class_name);
        return (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
            <Box
              sx={{
                width: 36, height: 36, flexShrink: 0,
                borderRadius: 1.25,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: `linear-gradient(135deg, ${meta.color}25, ${meta.color}10)`,
                border: `1px solid ${meta.color}33`,
                color: meta.color,
                position: "relative",
                "&::after": {
                  content: '""',
                  position: "absolute",
                  inset: -3,
                  borderRadius: 1.5,
                  border: `1px dashed ${meta.color}33`,
                  opacity: 0.6,
                },
              }}
            >
              <Hub sx={{ fontSize: 18 }} />
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Box
                sx={{
                  fontWeight: 700,
                  fontSize: "0.92rem",
                  color: "text.primary",
                  lineHeight: 1.15,
                }}
              >
                {row.name}
              </Box>
              <Box
                component="span"
                sx={{
                  fontFamily: FONT_MONO,
                  fontSize: "0.64rem",
                  color: "text.disabled",
                  letterSpacing: "0.04em",
                }}
              >
                EMBEDDING/{String(row.id).padStart(4, "0")}
              </Box>
            </Box>
          </Box>
        );
      },
    },
    {
      key: "class_name",
      label: t("embeddings.columns.class"),
      sortable: true,
      render: (row) => {
        const meta = providerMeta(row.class_name);
        return (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.4 }}>
            <MonoPill value={meta.short} color={meta.color} icon={Code} />
            <Box
              component="span"
              sx={{
                fontFamily: FONT_MONO,
                fontSize: "0.64rem",
                color: "text.disabled",
                letterSpacing: "0.02em",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: 220,
              }}
              title={row.class_name}
            >
              {row.class_name}
            </Box>
          </Box>
        );
      },
    },
    {
      key: "privacy",
      label: t("embeddings.columns.privacy"),
      sortable: true,
      render: (row) => {
        const isPublic = (row.privacy || "").toLowerCase() === "public";
        return isPublic
          ? <MonoPill value="PUBLIC"  color="#10b981" icon={Public} />
          : <MonoPill value="PRIVATE" color="#f59e0b" icon={Lock} />;
      },
    },
    {
      key: "dimension",
      label: t("embeddings.columns.dimensions"),
      sortable: true,
      align: "right",
      render: (row) => row.dimension
        ? <MonoPill value={`${row.dimension}-d`} color="#0891b2" icon={GridView} />
        : <Box component="span" sx={{ color: "text.disabled", fontFamily: FONT_MONO, fontSize: "0.74rem" }}>auto</Box>,
    },
  ];

  return (
    <Container>
      <PageHero
        icon={<Hub sx={{ color: "#fff" }} />}
        eyebrow="MODELS/EMBEDDINGS"
        title="Embeddings"
        subtitle="Vector encoders for semantic search and retrieval-augmented generation."
        stats={[
          { glyph: "◆", color: "#5eead4", label: `${aggregates.total} model${aggregates.total === 1 ? "" : "s"}` },
          { glyph: "⊞", color: "#a7f3d0", label: `${aggregates.providers.length} provider${aggregates.providers.length === 1 ? "" : "s"}` },
          ...(aggregates.publicCount > 0
            ? [{ glyph: "☼", color: "#bbf7d0", label: `${aggregates.publicCount} public` }]
            : []),
        ]}
        actions={
          isAdmin && (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => navigate("/embeddings/new")}
              sx={{
                textTransform: "none",
                fontWeight: 700,
                background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
                boxShadow: `0 4px 14px ${ACCENT}66`,
                "&:hover": {
                  background: `linear-gradient(135deg, ${ACCENT} 0%, #134e4a 100%)`,
                  boxShadow: `0 6px 18px ${ACCENT}88`,
                },
              }}
            >
              {t("embeddings.newBreadcrumb")}
            </Button>
          )
        }
      />

      <Grid container spacing={2} sx={{ mt: 1, mb: 2 }}>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Hub />}
            label="Total models"
            value={aggregates.total}
            accent={ACCENT}
            sub={`${aggregates.dimSet.size} unique dim${aggregates.dimSet.size === 1 ? "" : "s"}`}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Public />}
            label="Public"
            value={aggregates.publicCount}
            accent="#10b981"
            sub={aggregates.total ? `${((aggregates.publicCount / aggregates.total) * 100).toFixed(0)}% of catalogue` : "—"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Lock />}
            label="Private"
            value={aggregates.privateCount}
            accent="#f59e0b"
            sub={aggregates.privateCount ? "team-scoped" : "—"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Storage />}
            label="Providers"
            value={aggregates.providers.length}
            accent="#7c3aed"
            sub={aggregates.providers[0] ? `top: ${aggregates.providers[0].short}` : "—"}
          />
        </Grid>
      </Grid>

      {aggregates.providers.length > 0 && (
        <Box sx={{ mb: 2.5 }}>
          <ProviderDistribution providers={aggregates.providers} total={aggregates.total} />
        </Box>
      )}

      <DataList
        data={embeddings}
        columns={columns}
        searchKeys={["name", "class_name", "description"]}
        filters={[
          {
            key: "privacy",
            label: t("embeddings.columns.privacy"),
            options: [
              { value: "private", label: t("common.private") },
              { value: "public",  label: t("common.public") },
            ],
          },
        ]}
        onRowClick={(row) => navigate(`/embedding/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "id", direction: "desc" }}
        actions={(row) => (
          <>
            <Tooltip title={t("embeddings.actions.view")} arrow>
              <IconButton
                size="small"
                onClick={() => navigate(`/embedding/${row.id}`)}
                sx={{ color: ACCENT, "&:hover": { backgroundColor: ACCENT_SOFT } }}
              >
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            {isAdmin && (
              <>
                <Tooltip title={t("embeddings.actions.edit")} arrow>
                  <IconButton
                    size="small"
                    onClick={() => navigate(`/embedding/${row.id}/edit`)}
                    sx={{ color: "#0891b2", "&:hover": { backgroundColor: "rgba(8,145,178,0.10)" } }}
                  >
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={t("embeddings.actions.delete")} arrow>
                  <IconButton
                    size="small"
                    onClick={(e) => handleDelete(e, row)}
                    sx={{
                      color: "text.disabled",
                      "&:hover": { color: "#ef4444", backgroundColor: "rgba(239,68,68,0.08)" },
                    }}
                  >
                    <Delete fontSize="small" />
                  </IconButton>
                </Tooltip>
              </>
            )}
          </>
        )}
        emptyState={{
          icon: Hub,
          title: t("embeddings.emptyTitle"),
          message: t("embeddings.emptyMessage"),
          actionLabel: isAdmin ? t("embeddings.new") : undefined,
          actionIcon: <Add fontSize="small" />,
          onAction: isAdmin ? () => navigate("/embeddings/new") : undefined,
        }}
        emptyMessage={t("embeddings.noEmbeddings")}
      />
    </Container>
  );
}
