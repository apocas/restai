import { Fade, Grid } from "@mui/material";

import ProjectInfo from "./ProjectInfo";
import ProjectAI from "./ProjectAI";
import ProjectTokens from "./ProjectTokens";
import ProjectRAG from "./ProjectRAG";
import RAGUpload from "./RAGUpload";
import RAGBrowser from "./RAGBrowser";
import RAGRetrieval from "./RAGRetrieval";
import ProjectAgent from "./ProjectAgent";
import RouterDetails from "./RouterDetails";
import ProjectSecurity from "./ProjectSecurity";
import { useState, useEffect } from "react";
import { toast } from 'react-toastify';
import useAuth from "app/hooks/useAuth";

export default function ProjectDetails({ project, projects, info }) {
  const auth = useAuth();
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [tokens, setTokens] = useState({ "tokens": [] });

  const fetchTokens = () => {
    return fetch(url + "/projects/" + project.id + "/tokens/daily", { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            console.log(data);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((d) => setTokens(d.tokens)
      ).catch(err => {
        console.log(err.toString());
      });
  }

  useEffect(() => {
    if (project.name) {
      fetchTokens();
    }
  }, [project]);

  return (
    <Fade in timeout={300}>
      <Grid container spacing={3}>
        <Grid item lg={4} md={6} xs={12}>
          <ProjectInfo project={project} projects={projects} />
        </Grid>

        <Grid item lg={8} md={6} xs={12}>
          <ProjectAI project={project} projects={projects} />
        </Grid>

        <Grid item lg={4} md={6} xs={12}>
          <ProjectSecurity project={project} projects={projects} info={info} />
        </Grid>

        {project.type === "rag" && (
          <>
            <Grid item lg={4} md={6} xs={12}>
              <ProjectRAG project={project} projects={projects} />
            </Grid>
            <Grid item lg={4} md={6} xs={12}>
              <RAGUpload project={project} />
            </Grid>
            {project.chunks < 30000 && (
              <Grid item lg={12} md={12} xs={12}>
                <RAGBrowser project={project} />
              </Grid>
            )}
            <Grid item lg={12} md={12} xs={12}>
              <RAGRetrieval project={project} />
            </Grid>
          </>
        )}
        {project.type === "agent" && (
          <Grid item lg={4} md={6} xs={12}>
            <ProjectAgent project={project} projects={projects} />
          </Grid>
        )}
        {project.type === "router" && (
          <Grid item lg={8} md={6} xs={12}>
            <RouterDetails project={project} projects={projects} />
          </Grid>
        )}

        {tokens && tokens.length > 0 &&
          <Grid item lg={12} md={6} xs={12}>
            <ProjectTokens project={project} tokens={tokens} />
          </Grid>
        }
      </Grid>
    </Fade>
  );
}
