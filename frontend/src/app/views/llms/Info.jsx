import { useState, useEffect } from "react";
import { styled, Box } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import LLMInfo from "./components/LLMInfo";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import { toast } from 'react-toastify';

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

export default function LLMViewInfo() {
  const { id } = useParams();
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [projects, setProjects] = useState([]);
  const [llm, setLLM] = useState({});
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const auth = useAuth();

  const fetchLLM = (llmName) => {
    return fetch(url + "/llms/" + llmName, { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then((res) => res.json())
      .then((d) => {
        setLLM(d)
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

  const fetchInfo = async () => {
    try {
      const response = await fetch(url + "/info", {
        headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token })
      });
  
      const data = await response.json();
      if (!response.ok) {
        toast.error(data.detail);
        //throw new Error(response.statusText);
      } else {
        setInfo(data);
      }
    } catch (err) {
      toast.error(err.toString());
    }
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Project - ' + id;
    fetchLLM(id);
  }, [id]);

  useEffect(() => {
    fetchProjects();
    fetchInfo();
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "LLMs", path: "/llms" }, { name: id, path: "/llm/" + id }]} />
      </Box>

      <ContentBox className="analytics">
        <LLMInfo llm={llm} projects={projects} info={info} />
      </ContentBox>
    </Container>
  );
}
