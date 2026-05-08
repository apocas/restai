import { useState, useEffect } from "react";
import { styled } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import ProjectDetails from "./components/ProjectDetails";
import { useParams } from "react-router-dom";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

export default function ProjectInfo() {
  const { id } = useParams();
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState({});
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const auth = useAuth();

  const fetchProject = (projectID) => {
    auth.checkAuth();
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => {
        setProject(d)
        return d
      }).catch(() => {});
  }

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

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Project - ' + id;
    fetchProject(id);
  }, [id]);

  useEffect(() => {
    fetchProjects();
    fetchInfo();
  }, []);

  return (
    <Container>
      <ContentBox className="analytics">
        <ProjectDetails project={project} projects={projects} info={info} />
      </ContentBox>
    </Container>
  );
}
