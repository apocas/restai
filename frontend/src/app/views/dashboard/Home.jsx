import { useState, useEffect } from "react";
import { Card, Grid, styled, Box, Typography, Divider } from "@mui/material";
import ProjectsStats from "./shared/ProjectsStats";
import ProjectsTypesChart from "./shared/ProjectsTypesChart";
import ProjectsLLMsChart from "./shared/ProjectsLLMsChart";
import TopProjectsTable from "./shared/TopProjectsTable";
import DailyTokensChart from "./shared/DailyTokensChart";
import ActivityPulse from "./shared/ActivityPulse";
import TopLLMsChart from "./shared/TopLLMsChart";
import ProjectsTable from "./shared/ProjectsTable";
import OnboardingChecklist from "./shared/OnboardingChecklist";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
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
  const [projects, setProjects] = useState([]);
  const [topProjects, setTopProjects] = useState([]);
  const [summary, setSummary] = useState(null);
  const [dailyTokens, setDailyTokens] = useState([]);
  const [topLLMs, setTopLLMs] = useState([]);
  const auth = useAuth();
  const { platformCapabilities } = usePlatformCapabilities();
  const currency = platformCapabilities.currency || "EUR";

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Home";
    api.get("/projects", auth.user.token).then((d) => setProjects(d.projects)).catch(() => {});
    api.get("/statistics/top-projects?limit=5", auth.user.token).then((d) => setTopProjects(d.projects)).catch(() => {});
    api.get("/statistics/summary", auth.user.token).then((d) => setSummary(d)).catch(() => {});
    api.get("/statistics/daily-tokens?days=30", auth.user.token).then((d) => setDailyTokens(d.tokens || [])).catch(() => {});
    api.get("/statistics/top-llms?limit=10", auth.user.token).then((d) => setTopLLMs(d.llms || [])).catch(() => {});
  }, []);

  return (
    <Container>
      <Box sx={{ my: 3 }}>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[{ name: "Home", path: "/home" }]} />
        </Box>

        <ContentBox>
          {/* Onboarding (only shows on fresh installs) */}
          <OnboardingChecklist />

          {/* Section 1: Stats */}
          <ProjectsStats
            projects={projects}
            summary={summary}
            dailyTokens={dailyTokens}
            currency={currency}
          />

          {/* Section 2: Token & Cost Charts */}
          {dailyTokens.length > 0 && (
            <>
              <SectionTitle>Activity</SectionTitle>
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

          {/* Section 3: Distribution Row */}
          {(projects.length > 0 || topLLMs.length > 0) && (
            <>
              <SectionTitle>Distribution</SectionTitle>
              <Grid container spacing={3} sx={{ mb: 3 }}>
                <Grid item xs={12} md={4}>
                  <Card elevation={0} sx={chartCardSx}>
                    <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
                      Project Types
                    </Typography>
                    <ProjectsTypesChart projects={projects} height="280px" />
                  </Card>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Card elevation={0} sx={chartCardSx}>
                    <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
                      LLM Usage
                    </Typography>
                    <ProjectsLLMsChart projects={projects} height="280px" />
                  </Card>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Card elevation={0} sx={chartCardSx}>
                    <TopLLMsChart data={topLLMs} />
                  </Card>
                </Grid>
              </Grid>
            </>
          )}

          {/* Section 4: Tables */}
          <SectionTitle>Projects</SectionTitle>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <TopProjectsTable projects={topProjects} currency={currency} />
            </Grid>
            <Grid item xs={12} md={6}>
              <ProjectsTable
                projects={projects.slice(Math.max(projects.length - 5, 0)).reverse()}
                title="Latest Projects"
                compact
              />
            </Grid>
          </Grid>
        </ContentBox>
      </Box>
    </Container>
  );
}
