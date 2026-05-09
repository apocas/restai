import { useState, useEffect } from "react";
import { styled, Box } from "@mui/material";
import { Security } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import ProjectGuards from "./components/ProjectGuards";
import PageHero from "app/components/page/PageHero";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
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
          { glyph: "◆", color: "#fda4af", label: project.name || "—" },
          { glyph: "⚡", color: "#7dd3fc", label: project.type || "—" },
        ]}
        compact
      />
      <Box>
        {project.name && <ProjectGuards project={project} />}
      </Box>
    </Container>
  );
}
