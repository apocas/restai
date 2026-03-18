import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import ProjectsTableLibrary from "../dashboard/shared/ProjectsTableLibrary";
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


export default function Library() {
  const [projects, setProjects] = useState([]);
  const auth = useAuth();

  const fetchProjects = () => {
    return api.get("/projects?filter=public", auth.user.token)
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
        <Breadcrumb routeSegments={[{ name: "Projects", path: "/projects" }, { name: "Library", path: "/projects/library" }]} />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <ProjectsTableLibrary projects={projects.reverse()} />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
