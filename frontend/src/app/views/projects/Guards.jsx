import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import ProjectGuards from "./components/ProjectGuards";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

export default function ProjectGuardsView() {
  const { id } = useParams();
  const [project, setProject] = useState({});
  const auth = useAuth();

  useEffect(() => {
    api.get("/projects/" + id, auth.user.token)
      .then((d) => setProject(d))
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Guards - " + id;
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[
          { name: "Projects", path: "/projects" },
          { name: project.name || id, path: "/project/" + id },
          { name: "Guards", path: "/project/" + id + "/guards" },
        ]} />
      </Box>
      <ContentBox>
        <Grid container spacing={3}>
          <Grid item lg={12} md={12} sm={12} xs={12}>
            {project.name && <ProjectGuards project={project} />}
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
