import { useState, useEffect } from "react";
import { Box, Button, styled } from "@mui/material";
import { ArrowBack, AddCircle } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import ProjectNew from "./components/ProjectNew";
import TemplateGallery from "./components/TemplateGallery";
import PageHero from "app/components/page/PageHero";
import { FONT_MONO } from "app/components/page/pageStyles";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

export default function ProjectNewView() {
  const [projects, setProjects] = useState([]);
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [], "vectorstores": ["chroma"] });
  // undefined = gallery, null = scratch, object = template
  const [selectedTemplate, setSelectedTemplate] = useState(undefined);
  const auth = useAuth();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - New Project";
    api.get("/projects", auth.user.token).then((d) => setProjects(d.projects)).catch(() => {});
    api.get("/info", auth.user.token).then(setInfo).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const showGallery = selectedTemplate === undefined;
  const heroLabel = showGallery
    ? "templates"
    : (selectedTemplate ? selectedTemplate.name : "from scratch");

  return (
    <Container>
      <PageHero
        icon={<AddCircle sx={{ color: "#fff" }} />}
        eyebrow="PROJECTS/NEW"
        title="New Project"
        subtitle={
          showGallery
            ? "Pick a template to start from, or build one from scratch."
            : "Configure the project — name, team, type, and models."
        }
        stats={[
          { glyph: "◆", color: "#7dd3fc", label: heroLabel },
          ...(projects?.length
            ? [{ glyph: "⌬", color: "#a5b4fc", label: `${projects.length} existing` }]
            : []),
        ]}
        compact
      />

      <Box sx={{ mt: 2.5 }}>
        {showGallery ? (
          <TemplateGallery onSelect={(t) => setSelectedTemplate(t === null ? null : t)} />
        ) : (
          <>
            <Button
              startIcon={<ArrowBack />}
              onClick={() => setSelectedTemplate(undefined)}
              sx={{
                mb: 2,
                textTransform: "none",
                fontFamily: FONT_MONO,
                fontSize: "0.74rem",
                letterSpacing: "0.04em",
                color: "#0284c7",
                "&:hover": { backgroundColor: "rgba(2,132,199,0.08)" },
              }}
            >
              Back to Templates
            </Button>
            <ProjectNew projects={projects} info={info} template={selectedTemplate} />
          </>
        )}
      </Box>
    </Container>
  );
}
