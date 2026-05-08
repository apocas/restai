import { useState, useEffect } from "react";
import { Grid, styled } from "@mui/material";
import { Security } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import ProjectGuards from "./components/ProjectGuards";
import PageHero from "app/components/page/PageHero";
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

export default function ProjectGuardsView() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [project, setProject] = useState({});
  const auth = useAuth();

  useEffect(() => {
    api.get("/projects/" + id, auth.user.token)
      .then((d) => setProject(d))
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("projects.edit.tabs.guards") + " - " + id;
  }, [id, t]);

  return (
    <Container>
      <PageHero
        icon={<Security sx={{ color: "#fff" }} />}
        eyebrow={`PROJECT/${String(id).padStart(4, "0")}`}
        title="Guards"
        subtitle="Input/output guardrail checks and recent flags."
        stats={[
          { glyph: "◆", color: "#93c5fd", label: project.name || "—" },
          { glyph: "⚡", color: "#7dd3fc", label: project.type || "—" },
        ]}
        compact
      />
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
