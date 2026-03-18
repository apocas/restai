import { useState, useEffect } from "react";
import { styled, Box, Divider, Tab, Tabs } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import APIPython from "./components/APIPython";
import APIPHP from "./components/APIPHP";
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

export default function ProjectAPI() {
  const { id } = useParams();
  const [project, setProject] = useState({});
  const auth = useAuth();

  const [tabIndex, setTabIndex] = useState(0);
  const handleTabChange = (e, value) => setTabIndex(value);

  const fetchProject = (projectID) => {
    auth.checkAuth();
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => {
        setProject(d)
        return d
      }).catch(() => {});
  }

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - API - ' + id;
    fetchProject(id);
  }, [id]);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Projects", path: "/projects" }, { name: id, path: "/project/" + id }, { name: "API", path: "/project/" + id + "/api" }]} />
      </Box>

      <ContentBox className="analytics">
        <Tabs
          sx={{ mt: 2 }}
          value={tabIndex}
          onChange={handleTabChange}
          indicatorColor="primary"
          textColor="primary">
          {["Python", "PHP"].map((item, ind) => (
            <Tab key={ind} value={ind} label={item} sx={{ textTransform: "capitalize" }} />
          ))}
        </Tabs>

        <Divider sx={{ mb: "24px" }} />

        {tabIndex === 0 && <APIPython project={project}/>}
        {tabIndex === 1 && <APIPHP project={project}/>}
      </ContentBox>
    </Container>
  );
}
