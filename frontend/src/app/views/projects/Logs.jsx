import { useState, useEffect } from "react";
import { styled } from "@mui/material";
import { Article } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import ProjectLogs from "./components/ProjectLogs";
import PageHero from "app/components/page/PageHero";
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

export default function Logs() {
  const { id } = useParams();
  const [project, setProject] = useState({});
  const auth = useAuth();

  const fetchProject = (projectID) => {
    auth.checkAuth();
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => {
        setProject(d)
        return d
      }).catch(() => {});
  }

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Logs - ' + id;
    fetchProject(id);
  }, [id]);

  return (
    <Container>
      <PageHero
        icon={<Article sx={{ color: "#fff" }} />}
        eyebrow={`PROJECT/${String(id).padStart(4, "0")}`}
        title="Logs"
        subtitle="Inference history with status, latency, tokens and tool traces."
        stats={[
          { glyph: "◆", color: "#93c5fd", label: project.name || "—" },
          { glyph: "⚡", color: "#7dd3fc", label: project.type || "—" },
        ]}
        compact
      />

      <ContentBox className="analytics">
        <ProjectLogs project={project} />
      </ContentBox>
    </Container>
  );
}
