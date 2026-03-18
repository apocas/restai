import { Fragment, useState, useEffect } from "react";
import { Card, Grid, styled, useTheme, Box } from "@mui/material";
import ProjectsStats from "./shared/ProjectsStats";
import ProjectsTypesChart from "./shared/ProjectsTypesChart";
import ProjectsLLMsChart from "./shared/ProjectsLLMsChart";
import ProjectsTable from "./shared/ProjectsTable";
import TopProjectsTable from "./shared/TopProjectsTable";
import DailyTokensChart from "./shared/DailyTokensChart";
import TopLLMsChart from "./shared/TopLLMsChart";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import api from "app/utils/api";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const Title = styled("span")(() => ({
  fontSize: "1rem",
  fontWeight: "500",
  marginRight: ".5rem",
  textTransform: "capitalize"
}));

const SubTitle = styled("span")(({ theme }) => ({
  fontSize: "0.875rem",
  color: theme.palette.text.secondary
}));

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

export default function Analytics() {
  const { palette } = useTheme();
  const [projects, setProjects] = useState([]);
  const [topProjects, setTopProjects] = useState([]);
  const [summary, setSummary] = useState(null);
  const [dailyTokens, setDailyTokens] = useState([]);
  const [topLLMs, setTopLLMs] = useState([]);
  const auth = useAuth();
  const { platformCapabilities } = usePlatformCapabilities();
  const currency = platformCapabilities.currency || "EUR";

  const fetchProjects = () => {
    return api.get("/projects", auth.user.token)
      .then((d) => {
        setProjects(d.projects)
      }).catch(() => {});
  }

  const fetchTopProjects = () => {
    return api.get("/statistics/top-projects", auth.user.token)
      .then((d) => {
        setTopProjects(d.projects)
      }).catch(() => {});
  }

  const fetchSummary = () => {
    return api.get("/statistics/summary", auth.user.token)
      .then((d) => setSummary(d))
      .catch((err) => console.error("Failed to fetch summary:", err));
  };

  const fetchDailyTokens = () => {
    return api.get("/statistics/daily-tokens?days=30", auth.user.token)
      .then((d) => setDailyTokens(d.tokens || []))
      .catch((err) => console.error("Failed to fetch daily tokens:", err));
  };

  const fetchTopLLMs = () => {
    return api.get("/statistics/top-llms?limit=10", auth.user.token)
      .then((d) => setTopLLMs(d.llms || []))
      .catch((err) => console.error("Failed to fetch top LLMs:", err));
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Home';
    fetchProjects();
    fetchTopProjects();
    fetchSummary();
    fetchDailyTokens();
    fetchTopLLMs();
  }, []);

  return (
    <Container>
      <Box sx={{ my: 3 }}>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[{ name: "Home", path: "/home" }]} />
        </Box>

        <ContentBox className="analytics">
          <Grid container spacing={3}>
            <Grid item lg={8} md={8} sm={12} xs={12}>
              <ProjectsStats projects={projects} summary={summary} currency={currency} />
              <DailyTokensChart data={dailyTokens} currency={currency} />
              <TopProjectsTable projects={topProjects} currency={currency} />
              <ProjectsTable projects={projects.slice(Math.max(projects.length - 5, 0)).reverse()} title={"Latest 5 Projects"} />
            </Grid>

            <Grid item lg={4} md={4} sm={12} xs={12}>
              <Card sx={{ px: 3, py: 2, mb: 3 }}>
                <Title>Projects</Title>
                <SubTitle>Types</SubTitle>

                <ProjectsTypesChart
                  projects={projects}
                  height="300px"
                  color={[palette.primary.dark, palette.primary.main, palette.primary.light]}
                />
              </Card>

              <Card sx={{ px: 3, py: 2, mb: 3 }}>
                <Title>Projects</Title>
                <SubTitle>LLMs</SubTitle>

                <ProjectsLLMsChart
                  projects={projects}
                  height="300px"
                  color={[palette.primary.dark, palette.primary.main, palette.primary.light]}
                />
              </Card>

              <TopLLMsChart data={topLLMs} />
            </Grid>
          </Grid>
        </ContentBox>
      </Box>
    </Container>
  );
}
