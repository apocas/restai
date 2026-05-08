import { useState, useEffect } from "react";
import { Grid, styled } from "@mui/material";
import { Edit } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import ProjectEdit from "./components/ProjectEdit";
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


export default function ProjectNewView() {
  const { id } = useParams();
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState({});
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const auth = useAuth();


  const fetchProjects = () => {
    return api.get("/projects", auth.user.token)
      .then((d) => {
        setProjects(d.projects)
      })
      .catch(() => {});
  }

  const fetchInfo = () => {
    return api.get("/info", auth.user.token)
      .then((d) => setInfo(d))
      .catch(() => {});
  }

  const fetchProject = (projectID) => {
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => {
        setProject(d)
        return d
      }).catch(() => {});
  }

  useEffect(() => {
    fetchProject(id);
  }, [id]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Edit Project - ' + id;
    fetchProjects();
    fetchInfo();
  }, []);


  return (
    <Container>
      <PageHero
        icon={<Edit sx={{ color: "#fff" }} />}
        eyebrow={`PROJECT/${String(id).padStart(4, "0")}`}
        title="Edit Project"
        subtitle={project.human_name || project.name || "—"}
        stats={[
          { glyph: "◆", color: "#93c5fd", label: project.name || "—" },
          { glyph: "⚡", color: "#7dd3fc", label: project.type || "—" },
        ]}
        compact
      />

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <ProjectEdit project={project} projects={projects} info={info} />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
