import { useState, useEffect } from "react";
import { styled, Box } from "@mui/material";
import { Science } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import ProjectEvals from "./components/ProjectEvals";
import ProjectTrailBar from "./components/ProjectTrailBar";
import PageHero from "app/components/page/PageHero";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

export default function ProjectEvalsView() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [project, setProject] = useState({});
  const auth = useAuth();

  const fetchProject = (projectID) =>
    api.get("/projects/" + projectID, auth.user.token)
      .then((d) => setProject(d))
      .catch(() => {});

  useEffect(() => {
    fetchProject(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("projects.edit.tabs.evals") + " - " + id;
  }, [id, t]);

  return (
    <Container>
      <PageHero
        icon={<Science sx={{ color: "#fff" }} />}
        eyebrow={`PROJECT/${String(id).padStart(4, "0")}`}
        title="Evals"
        subtitle="Run evaluations against datasets and watch metric trends."
        stats={[
          { glyph: "◆", color: "#5eead4", label: project.name || "—" },
          { glyph: "⚡", color: "#7dd3fc", label: project.type || "—" },
        ]}
        compact
      />
      <ProjectTrailBar project={project} label="Evals" />
      <Box>
        {project.name && <ProjectEvals project={project} />}
      </Box>
    </Container>
  );
}
