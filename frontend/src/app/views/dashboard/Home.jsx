import { useState, useEffect } from "react";
import {
  Alert, Box, Button, Card, Grid, Typography, styled,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AddBoxOutlined, GraphicEq, DonutLarge, Workspaces, Hub,
} from "@mui/icons-material";
import AIHero from "./shared/AIHero";
import ProjectsStats from "./shared/ProjectsStats";
import ProjectsTypesChart from "./shared/ProjectsTypesChart";
import TopProjectsTable from "./shared/TopProjectsTable";
import DailyTokensChart from "./shared/DailyTokensChart";
import ActivityPulse from "./shared/ActivityPulse";
import ModelFleet from "./shared/ModelFleet";
import TopLLMsChart from "./shared/TopLLMsChart";
import ProjectsTable from "./shared/ProjectsTable";
import OnboardingChecklist from "./shared/OnboardingChecklist";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Per-section accents — each dashboard band gets its own hue so the
// page reads as a series of focused panels rather than a uniform wall.
const SECTION = {
  fleet:        { c: "#0284c7", soft: "rgba(2,132,199,0.10)" },  // sky — model fleet (matches LLMs page)
  activity:     { c: "#10b981", soft: "rgba(16,185,129,0.10)" }, // emerald — live throughput
  distribution: { c: "#7c3aed", soft: "rgba(124,58,237,0.10)" }, // violet — breakdowns
  projects:     { c: "#0891b2", soft: "rgba(8,145,178,0.10)" },  // cyan — workspaces
};

const TileCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = "#0284c7" }) => ({
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

function TileHeader({ icon, title, subtitle, accent = "#0284c7" }) {
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
    </Box>
  );
}

// Section marker — sharp colour rail + uppercase mono label. Replaces
// the previous Divider/overline pair with something more forensic.
function SectionTitle({ icon: Icon, label, accent }) {
  return (
    <Box
      sx={{
        mt: 4, mb: 2,
        display: "flex",
        alignItems: "center",
        gap: 1.25,
      }}
    >
      <Box sx={{ width: 14, height: 2, background: accent }} />
      {Icon && <Icon sx={{ fontSize: 16, color: accent }} />}
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.7rem",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          fontWeight: 800,
          color: accent,
        }}
      >
        {label}
      </Box>
      <Box
        sx={{
          flex: 1,
          height: 1,
          background: `linear-gradient(90deg, ${accent}33, transparent)`,
        }}
      />
    </Box>
  );
}

export default function Analytics() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [passwordWarning, setPasswordWarning] = useState(() => {
    try {
      const raw = sessionStorage.getItem("password_warning");
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  });
  const dismissPasswordWarning = () => {
    setPasswordWarning(null);
    try { sessionStorage.removeItem("password_warning"); } catch {}
  };
  const [topProjects, setTopProjects] = useState([]);
  const [summary, setSummary] = useState(null);
  const [dailyTokens, setDailyTokens] = useState([]);
  const [topLLMs, setTopLLMs] = useState([]);
  const [authSecretWeak, setAuthSecretWeak] = useState(false);
  const auth = useAuth();
  const { platformCapabilities } = usePlatformCapabilities();
  const currency = platformCapabilities.currency || "EUR";

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Home";
    api.get("/projects", auth.user.token)
      .then((d) => setProjects(d.projects || []))
      .catch(() => {})
      .finally(() => setProjectsLoaded(true));
    api.get("/statistics/top-projects?limit=5", auth.user.token).then((d) => setTopProjects(d.projects)).catch(() => {});
    api.get("/statistics/summary", auth.user.token).then(setSummary).catch(() => {});
    api.get("/statistics/daily-tokens?days=30", auth.user.token).then((d) => setDailyTokens(d.tokens || [])).catch(() => {});
    api.get("/statistics/top-llms?limit=10", auth.user.token).then((d) => setTopLLMs(d.llms || [])).catch(() => {});
    api.get("/info", auth.user.token, { silent: true })
      .then((d) => setAuthSecretWeak(!!d.auth_secret_weak))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Container>
      {/* Banners */}
      {passwordWarning && (
        <Alert
          severity="warning"
          onClose={dismissPasswordWarning}
          sx={{
            mb: 2,
            borderRadius: 2,
            border: "1px solid rgba(245,158,11,0.4)",
            backgroundColor: "rgba(245,158,11,0.06)",
          }}
        >
          {passwordWarning.message || `Your password is ${passwordWarning.password_age_days} days old. Please change it.`}
        </Alert>
      )}

      {auth.user?.is_admin && authSecretWeak && (
        <Alert
          severity="error"
          sx={{
            mb: 2,
            borderRadius: 2,
            border: "1px solid rgba(239,68,68,0.4)",
            backgroundColor: "rgba(239,68,68,0.06)",
          }}
        >
          {t("dashboard.authSecretWeak")}
        </Alert>
      )}

      {/* AI hero — kept intact, it's already on-brand. */}
      <AIHero
        summary={summary}
        dailyTokens={dailyTokens}
        modelsCount={topLLMs.length}
      />

      {/* Onboarding (only shows on fresh installs) */}
      <OnboardingChecklist />

      {/* Telemetry strip — left as-is (renders its own cards). */}
      <ProjectsStats
        projects={projects}
        summary={summary}
        dailyTokens={dailyTokens}
        currency={currency}
      />

      {/* ── MODEL FLEET ──────────────────────────────────────── */}
      {topLLMs.length > 0 && (
        <>
          <SectionTitle
            icon={Hub}
            label={t("dashboard.fleet.title") || "Model Fleet"}
            accent={SECTION.fleet.c}
          />
          <ModelFleet llms={topLLMs} />
        </>
      )}

      {/* ── ACTIVITY ─────────────────────────────────────────── */}
      {dailyTokens.length > 0 && (
        <>
          <SectionTitle
            icon={GraphicEq}
            label={t("dashboard.activity")}
            accent={SECTION.activity.c}
          />
          <Grid container spacing={3}>
            <Grid item xs={12} md={8}>
              <DailyTokensChart data={dailyTokens} />
            </Grid>
            <Grid item xs={12} md={4}>
              <ActivityPulse data={dailyTokens} />
            </Grid>
          </Grid>
        </>
      )}

      {/* ── DISTRIBUTION ─────────────────────────────────────── */}
      {(projects.length > 0 || topLLMs.length > 0) && (
        <>
          <SectionTitle
            icon={DonutLarge}
            label={t("dashboard.distribution")}
            accent={SECTION.distribution.c}
          />
          <Grid container spacing={3}>
            {projects.length > 0 && (
              <Grid item xs={12} md={6}>
                <TileCard elevation={0} accent={SECTION.distribution.c}>
                  <TileHeader
                    icon={<DonutLarge />}
                    title={t("dashboard.projectTypes")}
                    subtitle={`${projects.length} project${projects.length === 1 ? "" : "s"} · share by type`}
                    accent={SECTION.distribution.c}
                  />
                  <Box sx={{ p: 2 }}>
                    <ProjectsTypesChart projects={projects} height="280px" />
                  </Box>
                </TileCard>
              </Grid>
            )}
            {topLLMs.length > 0 && (
              <Grid item xs={12} md={6}>
                <TileCard elevation={0} accent={SECTION.distribution.c}>
                  <TileHeader
                    icon={<GraphicEq />}
                    title="Top LLMs"
                    subtitle={`${topLLMs.length} active · ranked by usage`}
                    accent={SECTION.distribution.c}
                  />
                  <Box sx={{ p: 2 }}>
                    <TopLLMsChart data={topLLMs} />
                  </Box>
                </TileCard>
              </Grid>
            )}
          </Grid>
        </>
      )}

      {/* ── PROJECTS ─────────────────────────────────────────── */}
      <SectionTitle
        icon={Workspaces}
        label={t("dashboard.projects")}
        accent={SECTION.projects.c}
      />
      {projectsLoaded && projects.length === 0 ? (
        <Card
          elevation={0}
          sx={{
            position: "relative",
            borderRadius: 14,
            border: `1px dashed ${SECTION.projects.c}55`,
            backgroundColor: "#fff",
            p: 6,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 2,
            textAlign: "center",
            overflow: "hidden",
            "&::before": {
              content: '""',
              position: "absolute",
              left: 0, right: 0, top: 0, height: 4,
              background: SECTION.projects.c,
              opacity: 0.6,
            },
          }}
        >
          <Box
            sx={{
              width: 72, height: 72,
              borderRadius: "50%",
              background: `radial-gradient(circle at 30% 30%, ${SECTION.projects.c}33, ${SECTION.projects.c}11 60%, transparent 70%)`,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              position: "relative",
              "&::before": {
                content: '""',
                position: "absolute",
                inset: -6,
                borderRadius: "50%",
                border: `1px dashed ${SECTION.projects.c}55`,
                animation: `${pulse} 3s ease-in-out infinite`,
              },
            }}
          >
            <AddBoxOutlined sx={{ fontSize: 36, color: SECTION.projects.c }} />
          </Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            {t("dashboard.noProjectsYet")}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480 }}>
            {t("dashboard.noProjectsDesc")}
          </Typography>
          <Button
            variant="contained"
            startIcon={<AddBoxOutlined />}
            onClick={() => navigate("/projects/new")}
            sx={{
              mt: 1,
              textTransform: "none",
              fontWeight: 700,
              background: `linear-gradient(135deg, ${SECTION.projects.c} 0%, #0e7490 100%)`,
              boxShadow: `0 4px 14px ${SECTION.projects.c}66`,
              "&:hover": {
                background: `linear-gradient(135deg, ${SECTION.projects.c} 0%, #155e75 100%)`,
                boxShadow: `0 6px 18px ${SECTION.projects.c}88`,
              },
            }}
          >
            {t("dashboard.createFirstProject")}
          </Button>
        </Card>
      ) : (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <TopProjectsTable projects={topProjects} currency={currency} />
          </Grid>
          <Grid item xs={12} md={6}>
            <ProjectsTable
              projects={projects.slice(Math.max(projects.length - 5, 0)).reverse()}
              title={t("dashboard.latestProjects")}
              compact
            />
          </Grid>
        </Grid>
      )}
    </Container>
  );
}
