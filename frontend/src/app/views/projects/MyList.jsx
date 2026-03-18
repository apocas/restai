import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import ProjectsTable from "../dashboard/shared/ProjectsTable";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import api from "app/utils/api";


const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));


export default function MyProjects() {
  const [projects, setProjects] = useState([]);
  const auth = useAuth();

  const fetchProjects = () => {
    return api.get("/projects", auth.user.token)
      .then((d) => {
        setProjects(d.projects)
      })
      .catch(() => {});
  }
  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Projects';
    fetchProjects();
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Projects", path: "/projects" }, { name: "My Projects", path: "/projects/my" }]} />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <ProjectsTable projects={projects.filter(project => project.users.some(user => user.username === auth.user.username)).reverse()} title={"My Projects"} />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
