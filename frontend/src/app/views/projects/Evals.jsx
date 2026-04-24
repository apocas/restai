import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import ProjectEvals from "./components/ProjectEvals";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
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

export default function ProjectEvalsView() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [project, setProject] = useState({});
  const auth = useAuth();

  const fetchProject = (projectID) => {
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => setProject(d))
      .catch(() => {});
  };

  useEffect(() => {
    fetchProject(id);
  }, [id]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("projects.edit.tabs.evals") + " - " + id;
  }, [id, t]);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb
          routeSegments={[
            { name: t("nav.projects"), path: "/projects" },
            { name: project.name || id, path: "/project/" + id },
            { name: t("projects.edit.tabs.evals"), path: "/project/" + id + "/evals" },
          ]}
        />
      </Box>

      <ContentBox>
        <Grid container spacing={3}>
          <Grid item lg={12} md={12} sm={12} xs={12}>
            {project.name && <ProjectEvals project={project} />}
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
