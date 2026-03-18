import { useState, useEffect } from "react";
import { styled, Box } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import ProjectLogs from "./components/ProjectLogs";
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
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Projects", path: "/projects" }, { name: id, path: "/project/" + id }, { name: "Logs", path: "/project/" + id + "/logs" }]} />
      </Box>

      <ContentBox className="analytics">
        <ProjectLogs project={project} />
      </ContentBox>
    </Container>
  );
}
