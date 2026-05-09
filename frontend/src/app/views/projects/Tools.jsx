import { useState, useEffect, useMemo } from "react";
import {
  Alert, Box, Card, Grid, InputAdornment, styled, TextField, Typography,
} from "@mui/material";
import {
  Search, Build, Block, Info,
  Language, Schedule, Forum, Web, Storage, Calculate,
  Terminal as TerminalIcon, FilterAlt,
} from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

// Tools = catalog / hub / inventory → cobalt reads as "operations
// console". Distinct from cron-amber, audit-indigo, logs-violet,
// routines-emerald, proxy-cyan, classifier-violet, guards-rose,
// evals-teal, gpu-orange.
const ACCENT = "#1d4ed8";        // blue-700
const ACCENT_DARK = "#1e3a8a";   // blue-900
const ACCENT_SOFT = "rgba(29,78,216,0.10)";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Per-category rail colour. Spread across the spectrum so each
// category section visually stands apart from the next as you scroll
// the catalogue.
const CATEGORIES = [
  { key: "browser",       icon: Language,     color: "#0ea5e9", match: /^browser_/,                                   requires: "browser"  },
  { key: "routines",      icon: Schedule,     color: "#f59e0b", match: /routine/i,                                    requires: null       },
  { key: "agentControl",  icon: TerminalIcon, color: "#a855f7", match: /^(terminal|create_tool)$/,                    requires: "docker"   },
  { key: "communication", icon: Forum,        color: "#10b981", match: /^send_/,                                      requires: "provider" },
  { key: "web",           icon: Web,          color: "#06b6d4", match: /^(crawler_|duckduckgo|wikipedia|whois_)/,     requires: null       },
  { key: "data",          icon: Storage,      color: "#ef4444", match: /^(data_parser|draw_image)$/,                  requires: null       },
];

const FALLBACK_CATEGORY = {
  key: "utility",
  icon: Calculate,
  color: "#64748b",
  requires: null,
};

function categorize(toolName) {
  for (const cat of CATEGORIES) if (cat.match.test(toolName)) return cat;
  return FALLBACK_CATEGORY;
}

function requirementsFor(toolName, toolEnabled) {
  const reqs = [];
  if (toolName === "terminal" || toolName === "create_tool") {
    reqs.push({ key: toolEnabled === false ? "requiresDocker" : "usesDocker", tone: "warn" });
  }
  if (/^browser_/.test(toolName))           reqs.push({ key: "usesBrowser",   tone: "info" });
  if (toolName === "browser_eval")          reqs.push({ key: "adminOptIn",    tone: "warn" });
  if (/^send_(email)$/.test(toolName))      reqs.push({ key: "needsSmtp",     tone: "neutral" });
  if (/^send_sms$/.test(toolName))          reqs.push({ key: "needsTwilio",   tone: "neutral" });
  if (/^send_telegram$/.test(toolName))     reqs.push({ key: "needsTelegram", tone: "neutral" });
  if (/^send_whatsapp$/.test(toolName))     reqs.push({ key: "needsWhatsApp", tone: "neutral" });
  if (/routine/i.test(toolName))            reqs.push({ key: "perProject",    tone: "info" });
  return reqs;
}

const TONE = {
  warn:    { c: "#d97706", bg: "rgba(217,119,6,0.10)" },
  info:    { c: "#0284c7", bg: "rgba(2,132,199,0.10)" },
  neutral: { c: "#475569", bg: "rgba(71,85,105,0.10)" },
};

// ── Tile card with per-category accent rail.
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
    background:
      "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
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

function TileHeader({ icon, title, subtitle, accent = ACCENT, action, count }) {
  return (
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
      {count != null && (
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            px: 1, py: 0.4,
            borderRadius: 0.75,
            backgroundColor: `${accent}10`,
            border: `1px solid ${accent}33`,
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            fontWeight: 700,
            color: accent,
          }}
        >
          {count}
        </Box>
      )}
      {action}
    </Box>
  );
}

function ToolCard({ tool, reqs, t, accent }) {
  const isDisabled = tool.enabled === false;
  return (
    <Box
      sx={{
        position: "relative",
        borderRadius: 2,
        border: `1px solid ${isDisabled ? "rgba(15,23,42,0.10)" : "rgba(15,23,42,0.08)"}`,
        backgroundColor: isDisabled ? "rgba(241,245,249,0.5)" : "#fff",
        p: 1.75,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        transition: "all 0.2s ease",
        opacity: isDisabled ? 0.65 : 1,
        overflow: "hidden",
        "&::before": isDisabled ? {} : {
          content: '""',
          position: "absolute",
          left: 0, top: 0, bottom: 0, width: 3,
          background: accent,
          opacity: 0.55,
        },
        "&:hover": isDisabled ? {} : {
          borderColor: `${accent}55`,
          boxShadow: `0 8px 22px ${accent}18`,
          "&::before": { opacity: 1 },
        },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.25, mb: 1 }}>
        <Box
          sx={{
            width: 30, height: 30, borderRadius: 1.25, flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: isDisabled ? "rgba(15,23,42,0.04)" : `${accent}15`,
            border: `1px solid ${isDisabled ? "rgba(15,23,42,0.06)" : `${accent}33`}`,
          }}
        >
          {isDisabled
            ? <Block sx={{ fontSize: 16, color: "text.disabled" }} />
            : <Build sx={{ fontSize: 16, color: accent }} />}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "0.84rem",
              fontWeight: 700,
              color: isDisabled ? "text.disabled" : "text.primary",
              wordBreak: "break-word",
              lineHeight: 1.2,
            }}
          >
            {tool.name}
          </Box>
          {isDisabled && (
            <Box
              sx={{
                mt: 0.5,
                display: "inline-flex",
                alignItems: "center",
                gap: 0.5,
                px: 0.7, py: 0.25,
                borderRadius: 0.75,
                backgroundColor: "rgba(148,163,184,0.12)",
                border: "1px solid rgba(148,163,184,0.35)",
              }}
            >
              <Box sx={{ width: 6, height: 6, borderRadius: "50%", background: "#94a3b8" }} />
              <Box
                component="span"
                sx={{
                  fontFamily: FONT_MONO,
                  fontSize: "0.6rem",
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  color: "#475569",
                  textTransform: "uppercase",
                }}
              >
                disabled
              </Box>
            </Box>
          )}
        </Box>
      </Box>
      {reqs.length > 0 && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1 }}>
          {reqs.map((r) => {
            const tone = TONE[r.tone] || TONE.neutral;
            return (
              <Box
                key={r.key}
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  px: 0.7, py: 0.2,
                  borderRadius: 0.75,
                  backgroundColor: tone.bg,
                  border: `1px solid ${tone.c}33`,
                  fontFamily: FONT_MONO,
                  fontSize: "0.6rem",
                  fontWeight: 700,
                  letterSpacing: "0.04em",
                  color: tone.c,
                  textTransform: "uppercase",
                }}
              >
                {t("tools.reqs." + r.key)}
              </Box>
            );
          })}
        </Box>
      )}
      <Typography
        variant="body2"
        sx={{
          color: isDisabled ? "text.disabled" : "text.secondary",
          whiteSpace: "pre-wrap",
          lineHeight: 1.5,
          fontSize: "0.81rem",
          flex: 1,
        }}
      >
        {tool.description}
      </Typography>
    </Box>
  );
}

export default function Tools() {
  const { t } = useTranslation();
  const [tools, setTools] = useState([]);
  const [search, setSearch] = useState("");
  const [activeCat, setActiveCat] = useState(null);
  const auth = useAuth();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("tools.breadcrumb");
    api.get("/tools/agent", auth.user.token)
      .then((d) => setTools(d || []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const groups = useMemo(() => {
    const q = search.toLowerCase();
    const matching = tools.filter((tl) =>
      !q ||
      tl.name.toLowerCase().includes(q) ||
      (tl.description || "").toLowerCase().includes(q)
    );
    const byKey = new Map();
    matching.forEach((tl) => {
      const cat = categorize(tl.name);
      if (!byKey.has(cat.key)) byKey.set(cat.key, { ...cat, tools: [] });
      byKey.get(cat.key).tools.push(tl);
    });
    const ordered = [];
    [...CATEGORIES, FALLBACK_CATEGORY].forEach((cat) => {
      const g = byKey.get(cat.key);
      if (g) {
        g.tools.sort((a, b) => a.name.localeCompare(b.name));
        ordered.push(g);
      }
    });
    return ordered;
  }, [tools, search]);

  // Pre-filter cohort counts for the chip filter strip — based on the
  // unfiltered set so toggling a chip doesn't drop the others.
  const allCounts = useMemo(() => {
    const m = new Map();
    tools.forEach((tl) => {
      const k = categorize(tl.name).key;
      m.set(k, (m.get(k) || 0) + 1);
    });
    return m;
  }, [tools]);

  const visibleGroups = activeCat ? groups.filter((g) => g.key === activeCat) : groups;
  const totalDisabled = tools.filter((tl) => tl.enabled === false).length;

  return (
    <Container>
      <PageHero
        icon={<Build sx={{ color: "#fff" }} />}
        eyebrow="OPS/TOOLS"
        title="Tools"
        subtitle="Built-in agent capabilities — browse the catalogue, see what each tool needs to run."
        stats={[
          { glyph: "◆", color: "#93c5fd", label: `${tools.length} available` },
          { glyph: "▸", color: "#bfdbfe", label: `${groups.length || CATEGORIES.length} categories` },
          ...(totalDisabled > 0 ? [{ glyph: "○", color: "#fca5a5", label: `${totalDisabled} disabled` }] : []),
        ]}
        compact
      />

      <Box sx={{ mt: 3 }}>
        {/* Search + info bar — sits in its own TileCard so the search */}
        {/* affordance reads as the page's primary control.            */}
        <TileCard elevation={0} accent={ACCENT}>
          <Box sx={{ p: 2 }}>
            <TextField
              fullWidth
              size="small"
              placeholder={t("tools.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search sx={{ fontSize: 18, color: ACCENT }} />
                  </InputAdornment>
                ),
                sx: {
                  fontFamily: FONT_MONO,
                  fontSize: "0.85rem",
                  "& fieldset": { borderColor: "rgba(15,23,42,0.10)" },
                  "&:hover fieldset": { borderColor: `${ACCENT}55` },
                  "&.Mui-focused fieldset": { borderColor: `${ACCENT}99 !important`, borderWidth: "1px !important" },
                },
              }}
            />

            {/* Category filter chips */}
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, mt: 1.5, alignItems: "center" }}>
              <Box
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.5,
                  fontFamily: FONT_MONO,
                  fontSize: "0.62rem",
                  letterSpacing: "0.08em",
                  fontWeight: 700,
                  color: "text.secondary",
                  textTransform: "uppercase",
                  pr: 0.5,
                }}
              >
                <FilterAlt sx={{ fontSize: 12 }} /> filter
              </Box>
              {[...CATEGORIES, FALLBACK_CATEGORY].map((cat) => {
                const cnt = allCounts.get(cat.key) || 0;
                if (cnt === 0) return null;
                const Icon = cat.icon;
                const isActive = activeCat === cat.key;
                return (
                  <Box
                    key={cat.key}
                    onClick={() => setActiveCat(isActive ? null : cat.key)}
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 0.6,
                      px: 0.85, py: 0.4,
                      borderRadius: 0.75,
                      cursor: "pointer",
                      backgroundColor: isActive ? `${cat.color}1c` : "transparent",
                      border: `1px solid ${isActive ? cat.color : `${cat.color}33`}`,
                      transition: "all 0.15s ease",
                      "&:hover": { backgroundColor: `${cat.color}12`, borderColor: `${cat.color}88` },
                    }}
                  >
                    <Icon sx={{ fontSize: 12, color: cat.color }} />
                    <Box
                      component="span"
                      sx={{
                        fontFamily: FONT_MONO,
                        fontSize: "0.66rem",
                        fontWeight: 700,
                        letterSpacing: "0.04em",
                        textTransform: "uppercase",
                        color: cat.color,
                      }}
                    >
                      {t("tools.categories." + cat.key + ".title")}
                    </Box>
                    <Box
                      component="span"
                      sx={{
                        fontFamily: FONT_MONO,
                        fontSize: "0.62rem",
                        fontWeight: 700,
                        color: cat.color,
                        opacity: 0.7,
                      }}
                    >
                      {cnt}
                    </Box>
                  </Box>
                );
              })}
              {activeCat && (
                <Box
                  onClick={() => setActiveCat(null)}
                  sx={{
                    cursor: "pointer",
                    fontFamily: FONT_MONO,
                    fontSize: "0.62rem",
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    color: "text.secondary",
                    textTransform: "uppercase",
                    px: 0.5,
                    "&:hover": { color: ACCENT },
                  }}
                >
                  ✕ clear
                </Box>
              )}
            </Box>
          </Box>
        </TileCard>

        {/* Info banner */}
        <Alert
          severity="info"
          icon={<Info fontSize="small" sx={{ color: ACCENT }} />}
          sx={{
            mt: 2,
            borderRadius: 2,
            border: `1px solid ${ACCENT}33`,
            backgroundColor: ACCENT_SOFT,
            color: ACCENT_DARK,
            fontSize: "0.82rem",
            "& .MuiAlert-icon": { alignItems: "center" },
          }}
        >
          {t("tools.info")}
        </Alert>

        {/* Categories list */}
        {visibleGroups.length === 0 ? (
          <TileCard elevation={0} accent={ACCENT} sx={{ mt: 2 }}>
            <Box
              sx={{
                py: 5,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 1.25,
              }}
            >
              <Box
                sx={{
                  width: 56, height: 56,
                  borderRadius: "50%",
                  background: ACCENT_SOFT,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  animation: `${pulse} 3s ease-out infinite`,
                }}
              >
                <Search sx={{ fontSize: 26, color: ACCENT }} />
              </Box>
              <Typography variant="body2" color="text.secondary">
                {search || activeCat ? t("tools.noMatch") : t("tools.noTools")}
              </Typography>
            </Box>
          </TileCard>
        ) : (
          visibleGroups.map((group) => {
            const GroupIcon = group.icon;
            return (
              <Box key={group.key} sx={{ mt: 2.5 }}>
                <TileCard elevation={0} accent={group.color}>
                  <TileHeader
                    icon={<GroupIcon />}
                    title={t("tools.categories." + group.key + ".title")}
                    subtitle={t("tools.categories." + group.key + ".subtitle")}
                    accent={group.color}
                    count={group.tools.length}
                  />
                  <Box sx={{ p: 2 }}>
                    <Grid container spacing={1.5}>
                      {group.tools.map((tool) => (
                        <Grid item xs={12} md={6} key={tool.name}>
                          <ToolCard
                            tool={tool}
                            reqs={requirementsFor(tool.name, tool.enabled)}
                            t={t}
                            accent={group.color}
                          />
                        </Grid>
                      ))}
                    </Grid>
                  </Box>
                </TileCard>
              </Box>
            );
          })
        )}
      </Box>
    </Container>
  );
}
