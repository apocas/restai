import { useState, useEffect } from "react";
import { Alert, Button, Card, Grid, styled, Box, Typography, Divider } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AddBoxOutlinedIcon from "@mui/icons-material/AddBoxOutlined";
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

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const SectionTitle = ({ children }) => (
  <Box sx={{ mb: 2, mt: 1 }}>
    <Typography variant="overline" color="text.secondary" fontWeight={600} letterSpacing={1.5}>
      {children}
    </Typography>
    <Divider sx={{ mt: 0.5 }} />
  </Box>
);

const chartCardSx = {
  p: 2.5,
  borderRadius: 3,
  border: "1px solid",
  borderColor: "divider",
};

export default function Analytics() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  // One-shot banner fed by JWTAuthContext. Stored in sessionStorage so
  // a page reload doesn't redisplay it; cleared after dismiss.
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
  // Weak-JWT-secret flag — fetched from authenticated /info (not /setup)
  // so the signal isn't discoverable by unauthenticated attackers.
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
    api.get("/statistics/summary", auth.user.token).then((d) => setSummary(d)).catch(() => {});
    api.get("/statistics/daily-tokens?days=30", auth.user.token).then((d) => setDailyTokens(d.tokens || [])).catch(() => {});
    api.get("/statistics/top-llms?limit=10", auth.user.token).then((d) => setTopLLMs(d.llms || [])).catch(() => {});
    // /info exposes the admin-only auth_secret_weak flag. Non-admins
    // get False from the backend regardless, so we can call it
    // unconditionally.
    api.get("/info", auth.user.token, { silent: true })
      .then((d) => setAuthSecretWeak(!!d.auth_secret_weak))
      .catch(() => {});
  }, []);

  return (
    <Container>
      <Box sx={{ my: 3 }}>
        <ContentBox>
          {passwordWarning && (
            <Alert
              severity="warning"
              onClose={dismissPasswordWarning}
              sx={{ mb: 2 }}
            >
              {passwordWarning.message || `Your password is ${passwordWarning.password_age_days} days old. Please change it.`}
            </Alert>
          )}

          {/* Weak JWT signing secret — only rendered to admins. */}
          {auth.user?.is_admin && authSecretWeak && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {t("dashboard.authSecretWeak")}
            </Alert>
          )}

          {/* AI hero banner replaces the old breadcrumb+title */}
          <AIHero
            summary={summary}
            dailyTokens={dailyTokens}
            modelsCount={topLLMs.length}
          />

          {/* Onboarding (only shows on fresh installs) */}
          <OnboardingChecklist />

          {/* Telemetry stat row with embedded sparklines */}
          <ProjectsStats
            projects={projects}
            summary={summary}
            dailyTokens={dailyTokens}
            currency={currency}
          />

          {/* Model Fleet — AI-specific replacement for the old distribution row */}
          {topLLMs.length > 0 && (
            <Box sx={{ mb: 3 }}>
              <ModelFleet llms={topLLMs} />
            </Box>
          )}

          {/* Activity: token throughput + pulse */}
          {dailyTokens.length > 0 && (
            <>
              <SectionTitle>{t("dashboard.activity")}</SectionTitle>
              <Grid container spacing={3} sx={{ mb: 3 }}>
                <Grid item xs={12} md={8}>
                  <DailyTokensChart data={dailyTokens} />
                </Grid>
                <Grid item xs={12} md={4}>
                  <ActivityPulse data={dailyTokens} />
                </Grid>
              </Grid>
            </>
          )}

          {/* Project-mix donut + Top LLMs bar */}
          {(projects.length > 0 || topLLMs.length > 0) && (
            <>
              <SectionTitle>{t("dashboard.distribution")}</SectionTitle>
              <Grid container spacing={3} sx={{ mb: 3 }}>
                {projects.length > 0 && (
                  <Grid item xs={12} md={6}>
                    <Card elevation={0} sx={chartCardSx}>
                      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
                        {t("dashboard.projectTypes")}
                      </Typography>
                      <ProjectsTypesChart projects={projects} height="280px" />
                    </Card>
                  </Grid>
                )}
                {topLLMs.length > 0 && (
                  <Grid item xs={12} md={6}>
                    <Card elevation={0} sx={chartCardSx}>
                      <TopLLMsChart data={topLLMs} />
                    </Card>
                  </Grid>
                )}
              </Grid>
            </>
          )}

          {/* Section 4: Tables / empty state */}
          <SectionTitle>{t("dashboard.projects")}</SectionTitle>
          {projectsLoaded && projects.length === 0 ? (
            <Card
              elevation={0}
              sx={{
                p: 5,
                borderRadius: 3,
                border: "1px dashed",
                borderColor: "divider",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 1.5,
                textAlign: "center",
              }}
            >
              <AddBoxOutlinedIcon sx={{ fontSize: 56, color: "text.secondary" }} />
              <Typography variant="h6" fontWeight={600}>{t("dashboard.noProjectsYet")}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480 }}>
                {t("dashboard.noProjectsDesc")}
              </Typography>
              <Button
                variant="contained"
                startIcon={<AddBoxOutlinedIcon />}
                onClick={() => navigate("/projects/new")}
                sx={{ mt: 1 }}
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
        </ContentBox>
      </Box>
    </Container>
  );
}
