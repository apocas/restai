import { useState, useEffect } from "react";
import { styled, Box, Card } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import { MatxSidenavContent } from "app/components/MatxSidenav";
import { MatxSidenavContainer } from "app/components/MatxSidenav";
import ChatContainer from "./components/ChatContainer";
import { toast } from 'react-toastify';

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));


export default function Playground() {
  const { id } = useParams();
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState({});
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const auth = useAuth();

  const fetchProject = (projectID) => {
    return fetch(url + "/projects/" + projectID, { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then((res) => res.json())
      .then((d) => {
        setProject(d)
        return d
      }).catch(err => {
        toast.error(err.toString());
      });
  }

  const fetchProjects = () => {
    return fetch(url + "/projects", { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((d) => {
        setProjects(d.projects)
      }
      ).catch(err => {
        toast.error(err.toString());
      });
  }

  const fetchInfo = () => {
    return fetch(url + "/info", { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((d) => setInfo(d)
      ).catch(err => {
        toast.error(err.toString());
      });
  }

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Playground - ' + id;
    fetchProject(id);
  }, [id]);

  useEffect(() => {
    fetchProjects();
    fetchInfo();
  }, []);


  return (
    <Container>
      <Box className="breadcrumb">
                <Breadcrumb routeSegments={[{ name: "Projects", path: "/projects" }, { name: id, path: "/project/" + id }, { name: "Playground", path: "/project/" + id + "/playground" }]} />
      </Box>

      <Card elevation={6}>
        <MatxSidenavContainer>
          <MatxSidenavContent>
            <ChatContainer project={project}/>
          </MatxSidenavContent>
        </MatxSidenavContainer>
      </Card>
    </Container>

  );
}
