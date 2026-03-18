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
import { toast } from 'react-toastify';
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
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [projects, setProjects] = useState([]);
  const [topProjects, setTopProjects] = useState([]);
  const [summary, setSummary] = useState(null);
  const [dailyTokens, setDailyTokens] = useState([]);
  const [topLLMs, setTopLLMs] = useState([]);
  const auth = useAuth();
  const { platformCapabilities } = usePlatformCapabilities();
  const currency = platformCapabilities.currency || "EUR";

  const fetchProjects = () => {
    return fetch(url + "/projects", {
      headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }),
      credentials: 'include'
    })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((d) => {
        setProjects(d.projects)
      }
      ).catch(err => {
        toast.error(err.toString());
      });
  }

  const fetchTopProjects = () => {
    return fetch(url + "/statistics/top-projects", {
      headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }),
      credentials: 'include'
    })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((d) => {
        setTopProjects(d.projects)
      }
      ).catch(err => {
        toast.error(err.toString());
      });
  }

  const fetchSummary = () => {
    return fetch(url + "/statistics/summary", {
      headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }),
      credentials: 'include'
    })
      .then((r) => { if (!r.ok) throw Error(r.statusText); return r.json(); })
      .then((d) => setSummary(d))
      .catch((err) => console.error("Failed to fetch summary:", err));
  };

  const fetchDailyTokens = () => {
    return fetch(url + "/statistics/daily-tokens?days=30", {
      headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }),
      credentials: 'include'
    })
      .then((r) => { if (!r.ok) throw Error(r.statusText); return r.json(); })
      .then((d) => setDailyTokens(d.tokens || []))
      .catch((err) => console.error("Failed to fetch daily tokens:", err));
  };

  const fetchTopLLMs = () => {
    return fetch(url + "/statistics/top-llms?limit=10", {
      headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }),
      credentials: 'include'
    })
      .then((r) => { if (!r.ok) throw Error(r.statusText); return r.json(); })
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
