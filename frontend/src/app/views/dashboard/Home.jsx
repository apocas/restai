import { Fragment, useState, useEffect } from "react";
import { Card, Grid, styled, useTheme, Box } from "@mui/material";
import ProjectsStats from "./shared/ProjectsStats";
import ProjectsTypesChart from "./shared/ProjectsTypesChart";
import ProjectsLLMsChart from "./shared/ProjectsLLMsChart";
import ProjectsTable from "./shared/ProjectsTable";
import TopProjectsTable from "./shared/TopProjectsTable";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { toast } from 'react-toastify';

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
  const auth = useAuth();

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
    if (!auth.user.is_admin) return;

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

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Home';
    fetchProjects();
    fetchTopProjects();
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
              <ProjectsStats projects={projects} />
              {auth.user.is_admin && <TopProjectsTable projects={topProjects} />}
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
            </Grid>
          </Grid>
        </ContentBox>
      </Box>
    </Container>
  );
}
