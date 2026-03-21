import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import BlocklyEditor from "./components/BlocklyEditor";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams, useNavigate } from "react-router-dom";
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

export default function ProjectIDEView() {
  const { id } = useParams();
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState({});
  const auth = useAuth();
  const navigate = useNavigate();

  const fetchProjects = () => {
    return api.get("/projects", auth.user.token)
      .then((d) => setProjects(d.projects))
      .catch(() => {});
  };

  const fetchProject = (projectID) => {
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => {
        setProject(d);
        return d;
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchProject(id);
  }, [id]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - IDE - ' + id;
    fetchProjects();
  }, []);

  const handleSave = (blocklyOpts) => {
    const opts = {
      name: project.name,
      options: {
        ...(project.options || {}),
        ...blocklyOpts,
      },
    };
    api.patch("/projects/" + project.id, opts, auth.user.token)
      .then(() => fetchProject(id))
      .catch(() => {});
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb
          routeSegments={[
            { name: "Projects", path: "/projects" },
            { name: project.name || id, path: "/project/" + id },
            { name: "IDE", path: "/project/" + id + "/ide" },
          ]}
        />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={12} sm={12} xs={12}>
            {project.name && (
              <BlocklyEditor
                project={project}
                projects={projects}
                onSave={handleSave}
              />
            )}
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
