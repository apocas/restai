import { useState, useEffect, useMemo } from "react";
import {
  Alert, Box, Card, Chip, Grid, InputAdornment, styled, TextField, Typography,
} from "@mui/material";
import {
  Search, Build, Block, Info,
  Language, Schedule, Forum, Web, Storage, Calculate,
  Terminal as TerminalIcon,
} from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

// Category taxonomy. Order of entries matters — first match wins, so
// keep the specific patterns (e.g. create_routine) above the catch-all
// "utility" bucket at the end.
const CATEGORIES = [
  {
    key: "browser",
    icon: Language,
    color: "#0ea5e9",
    match: /^browser_/,
    requires: "browser",
  },
  {
    key: "routines",
    icon: Schedule,
    color: "#1976d2",
    match: /routine/i,
    requires: null,
  },
  {
    key: "agentControl",
    icon: TerminalIcon,
    color: "#6366f1",
    match: /^(terminal|create_tool)$/,
    requires: "docker",
  },
  {
    key: "communication",
    icon: Forum,
    color: "#0891b2",
    match: /^send_/,
    requires: "provider",
  },
  {
    key: "web",
    icon: Web,
    color: "#2563eb",
    match: /^(crawler_|duckduckgo|wikipedia|whois_)/,
    requires: null,
  },
  {
    key: "data",
    icon: Storage,
    color: "#1e40af",
    match: /^(data_parser|draw_image)$/,
    requires: null,
  },
];

// Anything that doesn't match a category above lands here.
const FALLBACK_CATEGORY = {
  key: "utility",
  icon: Calculate,
  color: "#06b6d4",
  requires: null,
};

function categorize(toolName) {
  for (const cat of CATEGORIES) {
    if (cat.match.test(toolName)) return cat;
  }
  return FALLBACK_CATEGORY;
}

// Per-tool requirement chips. The /tools/agent endpoint only flags
// terminal/create_tool when docker is off; the rest of these are
// advisory so users know what they need to configure per tool.
function requirementsFor(toolName, toolEnabled) {
  const reqs = [];
  if (toolName === "terminal" || toolName === "create_tool") {
    reqs.push({ key: toolEnabled === false ? "requiresDocker" : "usesDocker", color: "warning" });
  }
  if (/^browser_/.test(toolName)) {
    reqs.push({ key: "usesBrowser", color: "info" });
  }
  if (toolName === "browser_eval") {
    reqs.push({ key: "adminOptIn", color: "warning" });
  }
  if (/^send_(email)$/.test(toolName)) {
    reqs.push({ key: "needsSmtp", color: "default" });
  }
  if (/^send_sms$/.test(toolName)) {
    reqs.push({ key: "needsTwilio", color: "default" });
  }
  if (/^send_telegram$/.test(toolName)) {
    reqs.push({ key: "needsTelegram", color: "default" });
  }
  if (/^send_whatsapp$/.test(toolName)) {
    reqs.push({ key: "needsWhatsApp", color: "default" });
  }
  if (/routine/i.test(toolName)) {
    reqs.push({ key: "perProject", color: "info" });
  }
  return reqs;
}

function ToolCard({ tool, reqs, t }) {
  return (
    <Card
      variant="outlined"
      sx={{
        p: 2,
        borderRadius: "10px",
        border: "1px solid",
        borderColor: "divider",
        opacity: tool.enabled === false ? 0.55 : 1,
        transition: "border-color 0.2s, box-shadow 0.2s",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        "&:hover": tool.enabled !== false
          ? { borderColor: "primary.main", boxShadow: "0 2px 10px rgba(25,118,210,0.08)" }
          : {},
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5 }}>
        <Box
          sx={{
            width: 32, height: 32, borderRadius: "8px", flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: (theme) => tool.enabled === false
              ? (theme.palette.mode === "dark" ? "rgba(150,150,150,0.15)" : "rgba(150,150,150,0.08)")
              : (theme.palette.mode === "dark" ? "rgba(25,118,210,0.18)" : "rgba(25,118,210,0.08)"),
          }}
        >
          {tool.enabled === false
            ? <Block sx={{ fontSize: 16, color: "text.disabled" }} />
            : <Build sx={{ fontSize: 16, color: "primary.main" }} />
          }
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="subtitle2"
            fontWeight={600}
            sx={{
              fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
              fontSize: "0.86rem",
              wordBreak: "break-word",
            }}
          >
            {tool.name}
          </Typography>
          {(reqs.length > 0) && (
            <Box sx={{ mt: 0.5, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {reqs.map((r) => (
                <Chip
                  key={r.key}
                  label={t("tools.reqs." + r.key)}
                  size="small"
                  color={r.color}
                  variant="outlined"
                  sx={{ fontSize: "0.65rem", height: 20 }}
                />
              ))}
            </Box>
          )}
        </Box>
      </Box>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{
          mt: 1.25,
          whiteSpace: "pre-wrap",
          lineHeight: 1.55,
          fontSize: "0.82rem",
          flex: 1,
        }}
      >
        {tool.description}
      </Typography>
    </Card>
  );
}

export default function Tools() {
  const { t } = useTranslation();
  const [tools, setTools] = useState([]);
  const [search, setSearch] = useState("");
  const auth = useAuth();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("tools.breadcrumb");
    api.get("/tools/agent", auth.user.token)
      .then((d) => setTools(d || []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  // Group tools by category, then alpha-sort within each group.
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
    // Keep group order aligned with CATEGORIES declaration order so
    // the page reads top-down from "headline" capabilities (browser,
    // routines) to infrastructure (agent control) to helpers.
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

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.projects"), path: "/projects" }, { name: t("tools.breadcrumb") }]} />
      </Box>

      <Box>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2, flexWrap: "wrap", gap: 2 }}>
          <Box>
            <Typography variant="h5" fontWeight={700}>{t("tools.title")}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t("tools.subtitle")}
            </Typography>
          </Box>
          <Chip label={t("tools.toolCount", { count: tools.length })} variant="outlined" size="small" />
        </Box>

        <Alert severity="info" icon={<Info fontSize="small" />} sx={{ mb: 3 }}>
          {t("tools.info")}
        </Alert>

        <TextField
          fullWidth
          size="small"
          placeholder={t("tools.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ mb: 3 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search fontSize="small" color="action" />
              </InputAdornment>
            ),
          }}
        />

        {groups.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 4 }}>
            {search ? t("tools.noMatch") : t("tools.noTools")}
          </Typography>
        ) : (
          groups.map((group) => {
            const GroupIcon = group.icon;
            return (
              <Box key={group.key} sx={{ mb: 4 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5 }}>
                  <Box
                    sx={{
                      width: 36, height: 36, borderRadius: 2,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      background: `${group.color}1a`,
                      color: group.color,
                    }}
                  >
                    <GroupIcon sx={{ fontSize: 20 }} />
                  </Box>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography
                      variant="overline"
                      sx={{
                        letterSpacing: 1.5,
                        fontWeight: 700,
                        fontSize: "0.72rem",
                        color: group.color,
                        lineHeight: 1,
                        display: "block",
                      }}
                    >
                      {t("tools.categories." + group.key + ".title")}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
                      {t("tools.categories." + group.key + ".subtitle")}
                    </Typography>
                  </Box>
                  <Chip
                    label={group.tools.length}
                    size="small"
                    sx={{
                      fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
                      fontWeight: 700,
                      background: `${group.color}1a`,
                      color: group.color,
                      border: `1px solid ${group.color}44`,
                    }}
                  />
                </Box>
                <Grid container spacing={2}>
                  {group.tools.map((tool) => (
                    <Grid item xs={12} md={6} key={tool.name}>
                      <ToolCard
                        tool={tool}
                        reqs={requirementsFor(tool.name, tool.enabled)}
                        t={t}
                      />
                    </Grid>
                  ))}
                </Grid>
              </Box>
            );
          })
        )}
      </Box>
    </Container>
  );
}
