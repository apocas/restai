import { useState, useEffect } from "react";
import { styled, Box } from "@mui/material";
import { Article } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import ProjectLogs from "./components/ProjectLogs";
import PageHero from "app/components/page/PageHero";
import { useParams } from "react-router-dom";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

export default function Logs() {
  const { id } = useParams();
  const [project, setProject] = useState({});
  const auth = useAuth();

  const fetchProject = (projectID) => {
    auth.checkAuth();
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => {
        setProject(d);
        return d;
      })
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Logs - " + id;
    fetchProject(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return (
    <Container>
      <PageHero
        icon={<Article sx={{ color: "#fff" }} />}
        eyebrow={`PROJECT/${String(id).padStart(4, "0")}`}
        title="Logs"
        subtitle="Inference history with status, latency, tokens and tool traces."
        stats={[
          { glyph: "◆", color: "#c4b5fd", label: project.name || "—" },
          { glyph: "⚡", color: "#7dd3fc", label: project.type || "—" },
        ]}
        compact
      />

      <Box>
        <ProjectLogs project={project} />
      </Box>
    </Container>
  );
}
